import gym
from gym import spaces
import numpy as np
# from os import path
import snakeoil3_gym as snakeoil3
import numpy as np
import copy
import collections as col
import os
import subprocess
import time
import math
import signal


class TorcsEnv:
    terminal_judge_start = 100  # Speed limit is applied after this step
    termination_limit_progress = 1  # [km/h], episode terminates if car is running slower than this limit
    default_speed = 300

    initial_reset = True

    def start_torcs_process(self):
        if self.torcs_proc is not None:
            os.killpg(os.getpgid(self.torcs_proc.pid), signal.SIGKILL)
            time.sleep(0.5)
            self.torcs_proc = None
        window_title = str(self.port)
        command = 'torcs -nofuel -nolaptime -title {} -p {}'.format(window_title, self.port)
        if self.vision is True:
            command += ' -vision'
        self.torcs_proc = subprocess.Popen([command], shell=True, preexec_fn=os.setsid)
        time.sleep(0.5)
        os.system('sh autostart.sh {}'.format(window_title))
        time.sleep(0.5)

    def __init__(self, vision=False, throttle=False, gear_change=False, port=3101):
       #print("Init")
        self.vision = vision
        self.throttle = throttle
        self.gear_change = gear_change
        self.port = port
        self.torcs_proc = None

        self.initial_run = True

        ##print("launch torcs")
        time.sleep(0.5)
        self.start_torcs_process()
        time.sleep(0.5)


    def step(self, a_t, early_stop):

        ## Create a desiered action with Effectors listed in same order as : arxiv.org/pdf/1304.1672.pdf table 3
        torcs_action = self.client.R.effectors # this is pass by reference so updating it updates the one in snakeoil

        # 1. accel in [0, 1]
        torcs_action.update({'accel': a_t[1]})

        # 2. brake in [0, 1]
        torcs_action.update({'brake': a_t[2]})

        # 3 clutch in [0, 1]
        # not implemented  ????
        torcs_action.update({'clutch': 0})

        # 4. gear in -1, 0, 1, ... , 6
        if(self.gear_change):
            gear = self.get_gear() #TODO this is just since the real automatic doesnt seem to work!!!!
        else:
            gear = 1
        torcs_action.update({'gear': gear})

        # 5. steer in [-1, 1]
        torcs_action.update({'steer': a_t[0]})

        # 6. focus in [-90,90] (list of 5 values) 1. should only be set once, 2. not reliable as sensors!
        #torcs_action.update({'focus': [-90,-45,0,45,90]})
        #torcs_action.update({'focus': [-50, -25, 0, 25, 50]}) # testing more forward vision!

        # 7. meta in 0,1 (restart race or not)
        torcs_action.update({'meta': 0})



        # Save the privious full-observation from torcs for the reward calculation
        prev_observation = copy.deepcopy(self.client.S.sensors)

        # Apply the Agent's action into torcs
        self.client.respond_to_server()

        # Get the response of TORCS
        self.client.get_servers_input()

        # Get the current full-observation from torcs
        # containing all 19 sensors from arxiv.org/pdf/1304.1672.pdf table 1/2 as key : value
        self.observation = self.client.S.sensors

        # calculate reward
        reward = self.calculate_reward(self.observation, prev_observation, early_stop)

        # scaled obs to send to agent
        obs = self.scale_observation(copy.deepcopy(self.client.S.sensors))

        done = (self.client.R.effectors['meta'] == 1)
        return obs, reward, done, {}

    def calculate_reward(self, obs, obs_pre, early_stop):
        # Reward setting Here #######################################
        # direction-dependent positive reward
        track = np.array(obs['track'])
        trackPos = np.array(obs['trackPos'])
        sp = np.array(obs['speedX'])

        # OLD reward function, kept for refrence
        progress_old = 3*sp*np.cos(obs['angle']) - np.abs(sp*np.sin(obs['angle'])) - sp * np.abs(obs['trackPos'])
        reward_old = progress_old

        # New reward function (parts)
        progress = 3*sp*np.cos(obs['angle'])
        penalty = -(obs['damage'] - obs_pre['damage']) - np.abs(sp*np.sin(obs['angle'])) - sp * np.abs(obs['trackPos'])

        # collision detection
        if obs['damage'] - obs_pre['damage'] > 0:
            reward_old = -(obs['damage'] - obs_pre['damage'])

        # Termination judgement #########################
        #if track.min() < 0:  # Episode is terminated if the car is out of track
        if (abs(track.any()) > 1 or abs(trackPos) > 1 and early_stop):  # Episode is terminated if the car is out of track
            reward_old = -200
            penalty -= progress
            print("META = 1 ... out of track")
            self.client.R.effectors['meta'] = 1

        if self.terminal_judge_start < self.time_step:  # Episode terminates if the progress of agent is small
            if((progress_old < self.termination_limit_progress) and early_stop ):
                print("META = 1 ... Minimal Progress!")
                self.client.R.effectors['meta'] = 1

        if np.cos(obs['angle']) < 0:  # Episode is terminated if the agent runs backward
            print("META = 1 ... Running backwards")
            self.client.R.effectors['meta'] = 1

        if self.client.R.effectors['meta'] is 1:  # Send a reset signal
            self.initial_run = False
            self.client.respond_to_server()

        reward = progress + penalty
        self.time_step += 1
        return [reward, progress, penalty, reward_old]

    def reset(self, relaunch=False):
        #print("Reset")

        self.time_step = 0

        if self.initial_reset is not True:
            self.client.R.effectors['meta'] = True
            self.client.respond_to_server()

            ## TENTATIVE. Restarting TORCS every episode suffers the memory leak bug!
            if relaunch is True:
                self.reset_torcs()
                print("### TORCS is RELAUNCHED ###")

        # Modify here if you use multiple tracks in the environment
        self.client = snakeoil3.Client(self.start_torcs_process, p=self.port)  # Open new UDP in vtorcs
        self.client.MAX_STEPS = np.inf

        client = self.client
        client.get_servers_input()  # Get the initial input from torcs

        self.observation = self.scale_observation(client.S.sensors)  # Get the current full-observation from torcs

        self.last_u = None

        self.initial_reset = False
        return self.observation

    def end(self):
        os.killpg(os.getpgid(self.torcs_proc.pid), signal.SIGKILL)

    def reset_torcs(self):
       #print("relaunch torcs")
        self.torcs_proc.terminate()
        time.sleep(0.5)
        self.start_torcs_process()
        time.sleep(0.5)


    def obs_vision_to_image_rgb(self, obs_image_vec):
        image_vec =  obs_image_vec
        r = image_vec[0:len(image_vec):3]
        g = image_vec[1:len(image_vec):3]
        b = image_vec[2:len(image_vec):3]

        test = list(zip(r,g,b))
        sz = (64, 64, 3)
        #r = np.array(r).reshape(sz)
        #g = np.array(g).reshape(sz)
        #b = np.array(b).reshape(sz)
        rgb = np.asarray(test).reshape((64,64,3))
        #print("OBS_VISION_TO_IMAGE_RGB rgb size = " + str(np.asarray(rgb).shape))

        return np.array(rgb, dtype=np.uint8)

    def scale_observation(self, raw_obs):
        ## listed all for future work but only scale the ones i need!!!
        raw_obs['angle'] = raw_obs['angle'] / math.pi
        # raw_obs['curLapTime']
        #raw_obs['damage'}]
        #raw_obs['distFromStart']
        #raw_obs['distRaced']
        raw_obs['focus'] = np.array(raw_obs['focus'])/200
        #raw_obs['fuel']
        #raw_obs['gear']
        #raw_obs['lastLapTime']
        raw_obs['opponents'] = np.array(raw_obs['opponents'])/200
        #raw_obs['racePos']
        raw_obs['rpm'] = raw_obs['rpm']/10000
        raw_obs['speedX'] = raw_obs['speedX'] / self.default_speed
        raw_obs['speedY'] = raw_obs['speedY'] / self.default_speed
        raw_obs['speedZ'] = raw_obs['speedZ'] / self.default_speed
        raw_obs['track'] = np.array(raw_obs['track']) / 200
        #raw_obs['trackPos'] = raw_obs['trackPos'] # should not be input to actor/critic, only in reward?!?!
        raw_obs['wheelSpinVel'] = np.array(raw_obs['wheelSpinVel']) / 100; #TODO Why? was like this in prev version?
        #raw_obs['z']

        if(self.vision):
            raw_obs['img'] = self.obs_vision_to_image_rgb(raw_obs['img'])

        return raw_obs

    def get_gear(self):
        speedX = self.client.S.sensors['speedX']
        gear = 1
        if speedX > 50:
            gear = 2
        if speedX > 80:
            gear = 3
        if speedX > 110:
            gear = 4
        if speedX > 140:
            gear = 5
        if speedX > 170:
            gear = 6
        return gear