#!/usr/bin/env bash


#r1: sett reward function to as similar to original as possible: (gym_torcs r1)
#a without gears
#b with gears

#r2: sett reward function to same as r1 but with new damage! (gym_torcs r2)
#a without gears
#b with gears

#r3: set reward function to same as r2 but with x3 progress! (gym_torcs r3)
#a without gears
#b with gears

#r4: Latest reward function (gym_torcs master)
#a without gears 
#b with gears
#AM : MEMORY LOGGING????

#r5: Latest reward function + Safety Critic v1
#a without gears
#b with gears

#r6: Latest reward function + Safety Critic v2
#a without gears
#b with gears

#r7: add safety critic gamma and test a couple:
#r71: safety_gamma = 0.99
#r72: safety_gamma = 0.97
#r73: safety_gamma = 0.95
#r74: safety_gamma = 0.93
#r75: safety_gamma = 0.91
