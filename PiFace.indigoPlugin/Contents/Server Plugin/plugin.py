#! /usr/bin/env python
# -*- coding: utf-8 -*-
#######################

import os
import sys
import socket
import indigo
import math
import decimal
import datetime
from xml.etree import ElementTree as ET
from ghpu import GitHubPluginUpdater

class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.updater = GitHubPluginUpdater(self)
        
        # Port
        self.listenPortDef = 8989
        self.listenPort    = 0
        
        self.apiVersion    = "2.0"
        self.localAddress  = ""
        # Pooling
        self.pollingInterval = 0

        # create empty device list      
        self.boardList = {}
        self.outputList = {}
        self.inputList = {}
    
        #sockRead = None
        #self.sockWrite = None

        self.socketBufferSize = 512
        self.socketStop       = False


    def __del__(self):
        indigo.PluginBase.__del__(self)     

    ###################################################################
    # Plugin
    ###################################################################

    def deviceStartComm(self, device):
        self.debugLog(u"Started device of type \"%s\"" % device.deviceTypeId + ": " + device.name)
        self.addDeviceToList (device)


    def deviceStopComm(self,device):
        if device.deviceTypeId == u"PiFaceBoard": 
            if device.id in self.boardList:
                self.debugLog("Stoping PiFace board device: " + device.name)
                del self.boardList[device.id]
        if device.deviceTypeId == u"PiFaceOutput": 
            if device.id in self.outputList:
                self.debugLog("Stoping PiFace mirror output device: " + device.name)
                del self.outputList[device.id]
        if device.deviceTypeId == u"PiFaceInput": 
            if device.id in self.inputList:
                self.debugLog("Stoping PiFace mirror input device: " + device.name)
                del self.inputList[device.id]

    def deviceCreated(self, device):
        self.debugLog(u"Created device of type \"%s\"" % device.deviceTypeId)
        self.addDeviceToList (device)

    def addDeviceToList(self,device):

        if device.deviceTypeId == u"PiFaceBoard": 
            self.updateDeviceState (device,'state' ,'off')
            propsAddress = ''
            propsPort = ''

            if device.id not in self.boardList: 
                propsAddress = device.pluginProps["address"]    
                propsPort    = device.pluginProps["port"]
                propsAddress = propsAddress.strip() 
                propsAddress = propsAddress.replace (' ','')
                self.boardList[device.id] = {'ref':device, 'address':propsAddress, 'port':propsPort, 'lastTimeSensor':datetime.datetime.now()}                  
        if device.deviceTypeId == u"PiFaceOutput":
            if device.id not in self.outputList:    
                self.outputList[device.id] = {'ref':device, 'boardSel':int(device.pluginProps["boardSel"]), 'pinSel':int(device.pluginProps["pinSel"])}
                device.pluginProps["address"] = 'output' + str(device.pluginProps["pinSel"])
        if device.deviceTypeId == u"PiFaceInput":
            if device.id not in self.inputList: 
                self.inputList[device.id] = {'ref':device, 'boardSel':int(device.pluginProps["boardSel"]), 'pinSel':int(device.pluginProps["pinSel"])}  
                device.pluginProps["address"] = 'input' + str(device.pluginProps["pinSel"])


    def startup(self):
        self.loadPluginPrefs()
        self.debugLog(u"startup called")

        # Obtain local address. 
        # This will identify a XBMC device running in same machine than Indigo
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("gmail.com",80))
        self.localAddress = s.getsockname()[0]
        s.close()

        self.debugLog("Local IP address: " + self.localAddress)
        self.updater.checkForUpdate()       
        
        
    def shutdown(self):
        self.debugLog(u"shutdown called")

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        valuesDict = pluginProps
        errorMsgDict = indigo.Dict()
        if self._devTypeIdIsMirrorDevice(typeId):
            if "boardSel" not in valuesDict:
                valuesDict["boardSel"] = 0
            if "pinSel" not in valuesDict:
                valuesDict["pinSel"] = 0
        return (valuesDict, errorMsgDict)

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.debugLog(u"validating device Prefs called")    
        if typeId == u"PiFaceBoard":
            self.debugLog(u"validating IP Address") 
            ipAdr = valuesDict[u'address']
            if ipAdr.count('.') != 3:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'address'] = u"This needs to be a valid IP address."
                return (False, valuesDict, errorMsgDict)
            if self.validateAddress (ipAdr) == False:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'address'] = u"This needs to be a valid IP address."
                return (False, valuesDict, errorMsgDict)
            self.debugLog(u"validating TCP Port")       
            tcpPort = valuesDict[u'port']   
            try:
                iPort = int(tcpPort)
                if iPort <= 0:
                    errorMsgDict = indigo.Dict()
                    errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
                    return (False, valuesDict, errorMsgDict)
            except Exception, e:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
                return (False, valuesDict, errorMsgDict)
        if typeId == u"PiFaceOutput":
            if int(valuesDict[u'boardSel']) <= 0:
                errorMsgDict[u'boardSel'] = u"Need to choose a PiFace device"
                return (False, valuesDict, errorMsgDict)
            if int(valuesDict[u'pinSel']) <= 0:
                errorMsgDict[u'pinSel'] = u"Need to choose a relay"
                return (False, valuesDict, errorMsgDict)    
            pass
        if typeId == u"PiFaceInput":
            if int(valuesDict[u'boardSel']) <= 0:
                errorMsgDict[u'boardSel'] = u"Need to choose a PiFace device"
                return (False, valuesDict, errorMsgDict)
            if int(valuesDict[u'pinSel']) <= 0:
                errorMsgDict[u'pinSel'] = u"Need to choose an input"
                return (False, valuesDict, errorMsgDict)        
            pass        
        return (True, valuesDict)

    def validatePrefsConfigUi(self, valuesDict):    
        self.debugLog(u"validating Prefs called")   
        tcpPort = valuesDict[u'listenPort'] 
        try:
            iPort = int(tcpPort)
            if iPort <= 0:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
                return (False, valuesDict, errorMsgDict)
        except Exception, e:
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
            return (False, valuesDict, errorMsgDict)
        return (True, valuesDict)

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
        if userCancelled is False:
            indigo.server.log ("Device preferences were updated.")

    def closedPrefsConfigUi ( self, valuesDict, UserCancelled):
        #   If the user saves the preferences, reload the preferences
        if UserCancelled is False:
            indigo.server.log ("Preferences were updated, reloading Preferences...")
            self.loadPluginPrefs()

    def loadPluginPrefs(self):
        # set debug option
        if 'debugEnabled' in self.pluginPrefs:
            self.debug = self.pluginPrefs['debugEnabled']
        else:
            self.debug = False
        
        self.listenPort = 0
            
        if self.pluginPrefs.has_key("listenPort"):
            self.listenPort = int(self.pluginPrefs["listenPort"])                   
        if self.listenPort <= 0:
            self.listenPort = self.listenPortDef

    def validateAddress (self,value):
        try:
            socket.inet_aton(value)
        except socket.error:
            return False
        return True

    ######################

    

    def menuGetDevsWithInputs(self, filter, valuesDict, typeId, elemId):
        menuList = []
        for dev in indigo.devices.iter("self"):
            if self._devTypeIdIsMirrorDevice(dev.deviceTypeId):
                continue    # skip -- we only want the main module devices
            menuList.append((dev.id, dev.name))
        return menuList

    def menuGetDevsWithOutputs(self, filter, valuesDict, typeId, elemId):
        menuList = []
        for dev in indigo.devices.iter("self"):
            if self._devTypeIdIsMirrorDevice(dev.deviceTypeId):
                continue    # skip -- we only want the main module devices
            menuList.append((dev.id, dev.name))
        return menuList

    def menuGetInputsForSelDev(self, filter, valuesDict, typeId, elemId):
        devId = int(valuesDict["boardSel"])
        return self.menuGetInputs(filter, valuesDict, typeId, devId)

    def menuGetOutputsForSelDev(self, filter, valuesDict, typeId, elemId):
        devId = int(valuesDict["boardSel"])
        return self.menuGetOutputs(filter, valuesDict, typeId, devId)

    def menuClearSelDev(self, valuesDict, typeId, elemId):
        valuesDict["pinSel"] = 0
        return valuesDict

    def menuGetInputs(self, filter, valuesDict, typeId, devId):
        inputs = []
        
        for pin in range(1, 9):
            labelVal = 'Input #' + str(pin)
            inputs.append((pin, labelVal))
        return inputs

    def menuGetOutputs(self, filter, valuesDict, typeId, devId):
        outputs = []
        
        for pin in range(1, 3):
            labelVal = 'Relay #' + str(pin)
            outputs.append((pin, labelVal))
        return outputs

    ###################################################################
    # Concurrent Thread. Socket 
    ###################################################################

    def runConcurrentThread(self):

        self.debugLog(u"Starting listening socket on port " + str(self.listenPort))
        
        theXML  = ""
        xCpu    = 0
        xTemp   = 0
        xIn     = ""
        xOut    = ""
        indigoDevice = None

        try:
            
            #sockRead=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockRead = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockRead.bind(("0.0.0.0",self.listenPort))
            #sockRead.settimeout(1)
            # Get socket IP Address
            sockRead.listen(6)
            self.socketOpen = True
            self.debugLog(u"Socket is ready")

        except socket.error:
            self.errorLog(u"Socket Setup Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))
        except Exception, e:
            self.errorLog (u"Error: " + str(e))
            pass

        try:
            while self.socketStop == False: 
                indigoDevice = None
                theXML       = ""

                try:
                    todayNow = datetime.datetime.now()
                    for piface in self.boardList:
                        lastTimeSensor = self.boardList[piface]['lastTimeSensor']
                        nextTimeSensor = lastTimeSensor + datetime.timedelta(seconds=60)
                        if nextTimeSensor <= todayNow:
                            indigoDevice = self.boardList[piface]['ref']
                            if indigoDevice.states['state'] == 'on':
                                self.updateDeviceState (indigoDevice,'state' ,'off')
                                self.updateDeviceState (indigoDevice,'cpu'   ,0)
                                self.updateDeviceState (indigoDevice,'temp'  ,0)
                                self.errorLog (indigoDevice.name + u" is lost!")

                except Exception,e:
                    self.errorLog (u"Error: " + str(e))
                    pass

                try:
                    # sock.recvfrom seems to only return complete log strings.  One log entry per return.
                    # Which is good, because log entries are not delimitted with any \n or \r characters.
                    # If responses were coming in with partial log entries and buffering was required
                    # to concatenate full strings it would be tricky to determine where one entry begins
                    # and the other ends.
                    socket_cliente, datos_cliente = sockRead.accept()
                    theXML                        = socket_cliente.recv (int(self.socketBufferSize))
                    #theXML, addr = sockRead.recvfrom (int(self.socketBufferSize))
                    theXML       = str(theXML)
                    theXML       = theXML.strip()   

                    addressFrom  = datos_cliente[0] #addr[0]
                    #self.debugLog(u"addressFrom: " + addressFrom)
                    #self.debugLog ("Socket. received: " + theXML + " from: " + str(addressFrom))
                    
                    for piface in self.boardList:
                        #if self.boardList[piface].deviceTypeId == u"PiFaceBoard": 
                        if self.boardList[piface]['address'] == addressFrom:
                            indigoDevice = self.boardList[piface]['ref']
                            self.boardList[piface]['lastTimeSensor'] = todayNow
                            #self.debugLog (u'Socket. Found PiFace board device "' + indigoDevice.name + '" for address ' + addressFrom)
                    if indigoDevice == None:
                        self.debugLog (u"Socket. Not found PiFace device for address " + addressFrom)
                except socket.timeout:
                    # No data was received, socket timed out or bailed for some other reason
                    # self.plugin.debugLog(u"Socket Timeout")
                    pass
                except socket.error:
                    self.errorLog(u"Socket Receive Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))    
                    pass
                except Exception,e:
                    self.errorLog (u"Error: " + str(e))
                    pass

                if (indigoDevice != None) and (theXML > ""):
                    theXML = '<?xml version="1.0"?>' + '<body>' + theXML + '</body>'
                    tree   = ET.fromstring (theXML)
                    xCpu  = tree.find('.//cpu').text
                    xTemp = tree.find('.//temp').text

                    self.updateDeviceState (indigoDevice,'cpu'  ,xCpu)  
                    self.updateDeviceState (indigoDevice,'temp' ,xTemp)
                    if indigoDevice.states['state'] != 'on':
                        self.updateDeviceState (indigoDevice,'state' ,'on')
                        indigo.server.log (indigoDevice.name + u" is connected!")
                    
                    xIn   = int(tree.find('.//in').text)
                    xOut  = int(tree.find('.//out').text)
                    
                    for pin in range (1,9):
                        state = 'input' + str(pin)
                        result = xIn & (1 << (pin - 1)); 
                        if result>0:
                            newValue=True

                        else:
                            newValue=False
                        if (newValue != indigoDevice.states[state]):
                            indigoDevice.updateStateOnServer(key=state, value=newValue) 
                            for piInput in self.inputList:
                                inputDevice = self.inputList[piInput]['ref']
                                boardSel    = self.inputList[piInput]['boardSel']
                                pinSel      = self.inputList[piInput]['pinSel']
                                if (pinSel == pin) and (int(boardSel) == indigoDevice.id):
                                    inputDevice.updateStateOnServer("onOffState", newValue)
                                    if newValue == True:
                                        dispValue='on'
                                    else:
                                        dispValue='off'
                                    indigo.server.log (u'received "' + inputDevice.name + '" status update is ' + dispValue)

                    for pin in range (1,3):
                        state = 'relay' + str(pin)
                        result = xOut & (1 << (pin - 1)); 
                        if result>0:
                            newValue=True
                        else:
                            newValue=False
                        if (newValue != indigoDevice.states[state]):
                            indigoDevice.updateStateOnServer(key=state, value=newValue)
                            for piOutput in self.outputList:
                                outputDevice = self.outputList[piOutput]['ref']
                                boardSel     = self.outputList[piOutput]['boardSel']
                                pinSel       = self.outputList[piOutput]['pinSel']
                                if (pinSel == pin) and (int(boardSel) == indigoDevice.id):
                                    outputDevice.updateStateOnServer("onOffState", newValue)
                                    if newValue == True:
                                        dispValue='on'
                                    else:
                                        dispValue='off'
                                    indigo.server.log (u'received "' + outputDevice.name + '" status update is ' + dispValue)
                

                self.sleep(0.05)
            if sockRead != None:
                sockRead.close
                sockRead = None

        except self.StopThread:
            if sockRead != None:
                sockRead.close
                sockRead = None
            pass
            self.debugLog(u"Exited listening socket")
        except Exception, e:
            self.errorLog (u"Error: " + str(e))
            pass    

    def stopConcurrentThread(self):
        self.socketStop = True
        self.stopThread = True
        self.debugLog(u"stopConcurrentThread called")
    

    def updateDeviceState(self,device,state,newValue):
        if (newValue != device.states[state]):
            device.updateStateOnServer(key=state, value=newValue)

    ###################################################################
    # Mirror relay
    ###################################################################

    def _devTypeIdIsMirrorDevice(self, typeId):
        return typeId in (u"PiFaceOutput", u"PiFaceInput")

    def _devTypeIdIsMirrorOutput(self, typeId):
        return typeId in (u"PiFaceOutput")

    def _devTypeIdIsMirrorInput(self, typeId):
        return typeId in (u"PiFaceInput")

    ###################################################################
    # Custom Action callbacks
    ###################################################################

    def actionControlSensor(self, action, dev):
        pass
        return
        
    def actionControlDimmerRelay(self, action, dev):
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.sendActionFromMirrorDev(dev, action)
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.sendActionFromMirrorDev(dev, action)
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            self.sendActionFromMirrorDev(dev, action)
        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.boardRequestStatus(dev)
            pass
            
    def boardRequestStatus(self,device):
        sockReqStatus = None
        if device == None:
            self.errorLog(u"no device specified")
            return

        if self._devTypeIdIsMirrorDevice (device.deviceTypeId):
            boardSel = int(device.pluginProps["boardSel"])
            for piface in self.boardList:
                if self.boardList[piface]['ref'].id == boardSel:
                    deviceBoard  = self.boardList[piface]["ref"]
        else:
            deviceBoard = device

        if deviceBoard == None:
            self.errorLog(u"no device specified")
            return
        if self._devTypeIdIsMirrorDevice(deviceBoard.deviceTypeId):
            self.errorLog(u"Expected PiFace board device type")
            return  

        addressWrite = deviceBoard.pluginProps["address"]   
        portWrite    = deviceBoard.pluginProps['port']
        cmdMessage = ''
        cmdMessage = cmdMessage + '<cmd>' + 'status'  + '</cmd>'

        try:
            sockError = False
            indigo.server.log(u'Sending "' + deviceBoard.name + '" request status')
            
            sock = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
            sock.settimeout (2)
            sock.connect (( addressWrite, int(portWrite) ))
            sock.send (cmdMessage)
            #sock.shutdown()
            sock.close()
            #self.sleep (0.1)
        except socket.timeout:
            # No data was received, socket timed out or bailed for some other reason
            self.errorLog(u"Socket Timeout")
            sockError = True
            pass
        except socket.error:
            sockError = True
            self.errorLog(u"Socket Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))    
            pass
        except Exception,e:
            sockError = True
            self.errorLog (u"Error: " + str(e))
            pass
        if sockError:
            self.updateDeviceState (deviceBoard,'state' ,'off')
            self.errorLog (deviceBoard.name + u" is lost!")


    def sendActionFromMirrorDev(self, device, action):
        cmdMessage = ""
        address = ''
        boardSel = 0
        pinSel = 0
        piface = 0
        portWrite = 0
        deviceBoard = None
        cmd = ''
        if device == None:
            self.errorLog(u"no device specified")
            return
        if not self._devTypeIdIsMirrorOutput(device.deviceTypeId):
            self.errorLog(u"Expected mirror relay device type")
            return  

        boardSel = int(device.pluginProps["boardSel"])
        pinSel   = int(device.pluginProps["pinSel"])

        if pinSel <=0:
            self.errorLog(u"Expected relay number")
            return
        if boardSel <=0:
            self.errorLog(u"Expected PiFace board")
            return

        for piface in self.boardList:
            if self.boardList[piface]['ref'].id == boardSel:
                deviceBoard  = self.boardList[piface]["ref"]
                addressWrite = self.boardList[piface]['address']
                portWrite    = self.boardList[piface]['port']

        if deviceBoard == None:
            self.errorLog (deviceBoard.name + u" is lost!")
            return  
        if deviceBoard.states['state'] == 'off':
            self.errorLog (deviceBoard.name + u" is lost!")
            return  

        if not(addressWrite > ''):
            self.errorLog(u"IP address not defined")
            return

        if int(portWrite) <=0:
            self.errorLog(u"Expected valid UDP Port")
            return

        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            cmd = 'ON'
        if action.deviceAction == indigo.kDeviceAction.TurnOff:
            cmd = 'OFF'
        if action.deviceAction == indigo.kDeviceAction.Toggle:
            if device.states["onOffState"]:
                cmd = 'OFF'
            else:
                cmd = 'ON'
        cmdMessage = ''
        cmdMessage = cmdMessage + '<cmd>' + cmd  + '</cmd>'
        cmdMessage = cmdMessage + '<out>' + str(pinSel - 1)  + '</out>'

        try:
            sockError = False
            indigo.server.log(u'Sending "' + device.name + '" ' + cmd.lower())
            
            sockWrite = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
            sockWrite.settimeout (2)
            sockWrite.connect (( addressWrite, int(portWrite) ))
            sockWrite.send (cmdMessage)
            #sockWrite.shutdown()
            sockWrite.close()
        except socket.timeout:
            # No data was received, socket timed out or bailed for some other reason
            self.errorLog(u"Socket Timeout")
            sockError = True
            pass
        except socket.error:
            sockError = True
            self.errorLog(u"Socket Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))    
            pass
        except Exception,e:
            sockError = True
            self.errorLog (u"Error: " + str(e))
            pass
        if sockError:
            self.updateDeviceState (deviceBoard,'state' ,'off')
            self.errorLog (deviceBoard.name + u" is lost!")

        return

    def dummyVal (self,dev):
        return

    ########################################
    # Menu Methods
    ########################################
    def toggleDebugging(self):
        if self.debug:
            indigo.server.log("Turning off debug logging")
            self.pluginPrefs["debugEnabled"] = False                
        else:
            indigo.server.log("Turning on debug logging")
            self.pluginPrefs["debugEnabled"] = True
        self.debug = not self.debug
        return
        
    def menuDeviceDiscovery(self):
        if self.discoveryWorking:
            return
        self.deviceDiscover()
        return
        
    def checkForUpdates(self):
        update = self.updater.checkForUpdate() 
        if (update != None):
            pass
        return    

    def updatePlugin(self):
        self.updater.update()
        