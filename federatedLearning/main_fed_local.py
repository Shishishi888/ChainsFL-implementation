# -*- coding: utf-8 -*-
# ******************************************************
# Filename     : main_fed_save.py
# Author       : Shuo Yuan 
# Email        : ishawnyuan@gmail.com
# Blog         : https://iyuanshuo.com
# Last modified: 2020-06-02 16:08
# Description  : 
# ******************************************************

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import copy
import numpy as np
import math
import time
from torchvision import datasets, transforms
import torch
from json import dumps
import os
import sys
import json

# Common Components
sys.path.append('../commonComponent')
import usefulTools

from utils.sampling import mnist_iid, mnist_noniid, cifar_iid
from utils.options import args_parser
from models.Update import LocalUpdate
from models.Nets import MLP, CNNMnist, CNNCifar
from models.Fed import FedAvg
from models.test import test_img
import buildModels


if __name__ == '__main__':

    while 1:
        iteration = 1
        taskRelInfo = {}
        # taskRelease info template {"taskID":"task1994","epoch":10,"status":"start","usersFrac":0.1}
        while 1:
            taskRelQue, taskRelQueStt = usefulTools.simpleQuery('taskRelease')
            if taskRelQueStt == 0:
                taskRelInfo = json.loads(taskRelQue)
                print('Latest task release status is %s!'%taskRelQue)
                break
        taskRelEpoch = int(taskRelInfo['epoch'])
        
        # task info template {"epoch":"0","status":training,"paras":"QmSaAhKsxELzzT1uTtnuBacgfRjhehkzz3ybwnrkhJDbZ2"}
        taskID = taskRelInfo['taskID']
        taskInfo = {}
        while 1:
            taskInQue, taskInQueStt = usefulTools.simpleQuery(taskID)
            if taskInQueStt == 0:
                taskInfo = json.loads(taskInQue)
                print('Latest task info is %s!\n'%taskInQue)
                break
        if taskInfo['status'] == 'done':
            print('*** The latest task has been completed! ***\n')
            time.sleep(5)
        else:
            currentEpoch = int(taskInfo['epoch']) + 1
            loss_train = []
            while currentEpoch <= taskRelEpoch:
                ## query the task info of current epoch
                while 1:
                    taskInQueEpo, taskInQueEpoStt = usefulTools.simpleQuery(taskID)
                    if taskInQueEpoStt == 0:
                        taskInfoEpo = json.loads(taskInQueEpo)
                        print('Latest task info is %s!\n'%taskInQueEpo)
                        break
                
                ## download the paras file of aggregated model for training in current epoch 
                aggBasModFil = './data/paras/aggBaseModel-epoch' + str(currentEpoch-1) + '.pkl'
                while 1:
                    aggBasMod, aggBasModStt = usefulTools.ipfsGetFile(taskInfoEpo['paras'], aggBasModFil)
                    if aggBasModStt == 0:
                        print('The paras file of aggregated model for epoch %d training has been downloaded!'%currentEpoch)
                        break
                    else:
                        print('Failed to download the paras file of aggregated model for epoch %d training!'%currentEpoch)
                # build network
                net_glob, args, dataset_train, dataset_test, dict_users = buildModels.modelBuild()
                net_glob.train()

                # copy weights and load the base model paras
                w_glob = net_glob.state_dict()
                net_glob.load_state_dict(torch.load(aggBasModFil))

                # Device name list
                with open('../commonComponent/selectedDeviceIdxs.txt', 'rb') as f:
                    idxs_users = pickle.load(f)
                ## init the list of device name
                allDeviceName = []
                for i in range(args.num_users):
                    allDeviceName.append("device"+("{:0>5d}".format(i)))
                ## select the device
                deviceSelected = []
                for idx in idxs_users:
                    deviceSelected.append(allDeviceName[idx])
                loss_locals = []
                for idx in idxs_users:
                    local = LocalUpdate(args=args, dataset=dataset_train, idxs=dict_users[idx])
                    w, loss = local.train(net=copy.deepcopy(net_glob).to(args.device))
                    loss_locals.append(copy.deepcopy(loss))
                    devLocFile = './data/local/' + deviceSelected[idx] + '-' + taskID + '-epoch' + str(currentEpoch) + '.pkl'
                    torch.save(w, devLocFile)
                    while 1:
                        localAdd, localAddStt = usefulTools.ipfsAddFile(devLocFile)
                        if localAddStt == 0:
                            print('%s has been added to the IPFS network!'%devLocFile)
                            print('And the hash value of this file is %s\n'%localAdd)
                        else:
                            print('Failed to add %s to the IPFS network!'%devLocFile)
                    while 1:
                        localRelease = subprocess.Popen(args=['../commonComponent/interRun.sh local '+deviceSelected[idx]+' '+taskID+' '+str(currentEpoch)+' '+localAdd], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
                        localOuts, localErrs = localRelease.communicate(timeout=10)
                        if localRelease.poll() == 0:
                            print(localOuts)
                            print('*** Local model train in epoch ' + str(currentEpoch) + ' of ' + deviceSelected[idx] + ' has been released! ***\n')
                            break
                        else:
                            print(localErrs)
                            print('*** Failed to release Local model train in epoch ' + str(currentEpoch) + ' of ' + deviceSelected[idx] + '! ***\n')
                            time.sleep(2)

                loss_avg = sum(loss_locals) / len(loss_locals)
                print('Epoch {:3d}, Average loss {:.3f}'.format(currentEpoch, loss_avg))
                loss_train.append(loss_avg)

            # plot loss curve
            plt.figure()
            plt.plot(range(len(loss_train)), loss_train)
            plt.ylabel('train_loss')
            plt.savefig('./save/fed_{}_{}_{}_C{}_iid{}_iteration{}.png'.format(args.dataset, args.model, args.epochs, args.frac, args.iid, iteration))
        iteration += 1
                
            # testing
            # net_glob.eval()
            # acc_train, loss_train = test_img(net_glob, dataset_train, args)
            # acc_test, loss_test = test_img(net_glob, dataset_test, args)
            # print("Training accuracy: {:.2f}".format(acc_train))
            # print("Testing accuracy: {:.2f}".format(acc_test))
