#!/usr/bin/env python

import os
import sys
import signal
import time
import logging
import datetime
import socket
import SocketServer
import threading
import pifacedigitalio as pfio
import subprocess 
import re
from ConfigParser import SafeConfigParser
import json
import logging
from daemon import Daemon
from xml.etree import ElementTree as ET
 
                       
class MainIndigo():

    def __init__(self):

        self.TEMP_MAX     = 78
        self.indigo_ip    = ''

        self.currentdir   = ''
        self.currentfile  = ''
        self.currentparm  = ''
        self.currentpath  = ''
 
        self.IntervalSoc  = 0
        self.IntervalCheck= 0
        self.PortRead     = 0
        self.PortWrite    = 0
        self.bufferSize   = 0
        self.addressWrite = ""
        self.addressRead  = ""
        self.inputList      = {}
        self.relayoffList   = {}       
        self.pulsecountList = {}
        
        self.relayoffFound = False
        self.pulsecountFound = False

        self.PIDThreadMain = 0
        self.ThreadCpu  = 0
        self.ThreadTemp = 0
        self.ThreadSock = 0
        
        self.DEBUG         = 1
        self.TERMINATE     = False
        self.REQUESTSTATUS = False
        self.EVENTINPUT    = 0
        self.EVENTOUTPUT   = 0
        self.TEMP_CUR      = 0
        self.CPU_USAGE     = 0
        self.PIN_INPUT     = '00000000'
        self.PIN_OUTPUT    = '00000000'
        self.TODAYNOW      = datetime.datetime.now()

    def shutdown(self):
        os.system("sudo /sbin/shutdown -h now")
    
    def computerTemp(self):  
        self.loggingDebug ("computerTemp: Thread started")

        TEMP_REGEX   = re.compile(r'temp=([\d\.]*)\'C')
        while True:
            if self.TERMINATE:
                break
            command  = "/opt/vc/bin/vcgencmd measure_temp"
            output   = subprocess.check_output(command, shell=True)
            matches  = re.findall(TEMP_REGEX, output)  
            self.TEMP_CUR = float(matches[0])
            for iter in range(1,100):
                if self.TERMINATE:
                    break
                time.sleep(0.1)
        
        Self.loggingDebug ("computerTemp: Thread terminating")
                     
    def computerCPU(self):
        CPU_PREV_IDLE = 0
        CPU_PREV_TOTAL = 0
    
        self.loggingDebug ("computerCPU: Thread started")        
        while True:
            if self.TERMINATE:
                break
            stat_fd = open('/proc/stat')
            stat_buf = stat_fd.readlines()[0].split()
            total = float(stat_buf[1]) + float(stat_buf[2]) + float(stat_buf[3]) + float(stat_buf[4]) + float(stat_buf[5]) + float(stat_buf[6]) + float(stat_buf[7])
            idle = float(stat_buf[4])
            stat_fd.close()
            diff_idle = idle - CPU_PREV_IDLE
            diff_total = total - CPU_PREV_TOTAL
            if diff_total > 0:
                usage = 1000.0 * (diff_total - diff_idle) / diff_total
                usage = usage / 10
                usage = round(usage, 1)
            else:
                usage = 100
            CPU_PREV_TOTAL = total
            CPU_PREV_IDLE = idle
            self.CPU_USAGE = usage
            for iter in range(1,100):
                if self.TERMINATE:
                    break
                time.sleep(0.1)       
        self.loggingDebug ("computerCPU: Thread terminating")
    
    def serverSock(self,Host,PortRead):       
        self.loggingDebug ("serverSock: Thread started")        
        try:
            logging.info ("serverSock. Startup at port " + str(PortRead))
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((Host, PortRead))
            server.listen(6)
            logging.info ("serverSock. Socket up and listening")
        except socket.error:
            logging.error ('serverSock. Error: ' + str(sys.exc_info()[1][1] ))
            pass        
        except Exception as e:
            logging.error ('serverSock. Error: ' + str(e))
            pass
                
        while True:
            if self.TERMINATE:
                break
            xCmd = ''
            xOut = ''
            try:
                socket_cliente, datos_cliente = server.accept()
                if self.TERMINATE:
                   break
                cmdMessage = socket_cliente.recv(128)
            except socket.error:
                logging.error ('serverSock. Error: ' + self.addressWrite + ":" + str(self.PortWrite) + ' ... ' + str(sys.exc_info()[1][1] ))
                pass    
            logging.info ("Mensaje recibido: " + cmdMessage)
            
            try:
                theXML = '<?xml version="1.0"?>' + '<body>' + cmdMessage + '</body>'
                tree   = ET.fromstring (theXML)
                xCmd   = tree.find('.//cmd').text
               
                xCmd   = xCmd.upper()
            except Exception as e:
                logging.error ('serverSock. Error: ' + str(e))
                pass                
            if xCmd in {'ON','OFF'}:    
                try:
                    xOut  = tree.find('.//out').text
                except Exception as e:
                    logging.error ('serverSock. Error: ' + str(e))
                    pass
                  
            try:
                if xCmd == 'ON':
                    #pfio.digital_write (int(xOut),1)
                    self.pfd.output_pins[int(xOut)].value = 1
                    self.EVENTOUTPUT = True
                    logging.info ("Set ON output " + xOut)
    
                elif xCmd == 'OFF':
                    #pfio.digital_write (int(xOut),0)
                    self.pfd.output_pins[int(xOut)].value = 0
                    self.EVENTOUTPUT += 1
                    logging.info ("Set OFF output " + xOut)
                elif xCmd == 'STATUS':
                    self.REQUESTSTATUS = True
                    logging.info ("Marked for request status")
                    pass
                elif xCmd == 'SHTDWN':
                    self.shutdown()
                    return
                elif xCmd == 'TERMINATE':
                    break
            except Exception as e:
                logging.error ('serverSock. Error: ' + str(e))
                pass
                
        server.close()   
        self.loggingDebug ("serverSock: Thread terminating")                  
        return
    
    
    def eventInputProcess(self,event):        
        #IODIR_FALLING_EDGE = IODIR_ON = 0
        #IODIR_RISING_EDGE = IODIR_OFF = 1
        #IODIR_BOTH = None
        
        pin = int(event.pin_num) + 1
        direction = event.direction
        
        if self.pulsecountFound:         
           if pin in self.pulsecountList:
               self.TODAYNOW = datetime.datetime.now()
               if direction == pfio.IODIR_ON:  #IODIR_FALLING_EDGE:
                  self.pulsecountList[pin]['received'] += 1
                  self.pulsecountList[pin]['lastreceived'] = self.TODAYNOW
                  if self.inputList[pin]['led'] == 0:
                    self.inputList[pin]['led'] = 1
                    self.EVENTINPUT += 1
               else:
                   self.checkSleepCounter(pin)
               return
        if direction == pfio.IODIR_ON:
            self.inputList[pin]['led'] = 1
        else:
            self.inputList[pin]['led'] = 0              
                
        self.EVENTINPUT += 1
        return

    def checkSleepCounter(self,pin):       
        if int(self.pfd.input_pins[pin - 1].value) == 1:
            self.pulsecountList[pin]['lastreceived'] = self.TODAYNOW
        else:
            timeInterval = self.pulsecountList[pin]['lastreceived'] + datetime.timedelta(seconds=2)
            if timeInterval < self.TODAYNOW:
                self.inputList[pin]['led'] = 0
                self.pulsecountList[pin]['lastreceived'] = self.TODAYNOW
                self.EVENTINPUT += 1
        return
        
    def checkSleepCounters(self):        
        if self.pulsecountFound:
            self.TODAYNOW = datetime.datetime.now()
            for pin in self.pulsecountList:
                self.checkSleepCounter(pin)
        return       
        
    def eventOutputProcess(self,event):
        self.EVENTOUTPUT += 1
        return  
        
    def getPinValue(self):
        if self.pulsecountFound:
            leds = ''
            for pin in range (1,8):
                vpin = "0"
                
                if pin in self.pulsecountList:
                    vpin = str(self.inputList[pin]['led'])
                else:
                    vpin = str(self.pfd.input_pins[pin -1].value)
                leds = vpin + leds
    
            self.PIN_INPUT  = str(int(leds,2)) 
        else:
            self.PIN_INPUT = str(self.pfd.input_port.value)
        self.PIN_OUTPUT = str(self.pfd.output_port.value)
        return
        
    def getParm(self): 
        self.IntervalSoc   = 10       
        self.IntervalCheck = 1 
        self.bufferSize    = 512

        parser = SafeConfigParser()
        parser.read(self.currentparm)

        if parser.has_option ('logging', 'debug'):
            self.DEBUG = int(parser.get('logging', 'debug'))
        if parser.has_option ('risk', 'maxtemp'):
            parmTemp = int(parser.get('risk', 'maxtemp'))   
            if parmTemp > 0:
               self.TEMP_MAX = parmTemp


        if parser.has_option ('indigo', 'address'):
            self.addressWrite = parser.get('indigo', 'address')
        else:
            self.addressWrite = "172.30.74.41"

        if parser.has_option ('indigo', 'port'):
            self.PortWrite = int(parser.get('indigo', 'port'))
        else:
            self.PortWrite = 8989 

        if parser.has_option ('listen', 'port'):    
            self.PortRead = int(parser.get('listen', 'port'))
        else:
            self.PortRead = 8989

        self.loggingInfo ('Indigo address = ' + self.addressWrite )
        self.loggingInfo ('Indigo port = '    + str(self.PortWrite) )
        self.loggingInfo ('Listening port = ' + str(self.PortWrite) )
        
        self.TODAYNOW = datetime.datetime.now()
        
        for pin in range (1,8):
            self.inputList[pin] = {'led': 0}
            
        for pin in range (1,8):
            label = 'input' + str(pin)
            if parser.has_option ('relayoff', label):                
                value = int (parser.get('relayoff', label))
                if value > 1:
                    value = 1
                if value < 0:
                    value = 0    
                self.relayoffList[pin] = {'poweroffvalue': value, 'previous': value}
                self.relayoffFound = True             
 
        for pin in self.relayoffList:
            if self.relayoffList[pin]['poweroffvalue'] == 1:
                self.loggingInfo ('Relays will switch off when input #' + str(pin) + ' becomes on')
            else:
                self.loggingInfo ('Relays will switch off when input #' + str(pin) + ' becomes off')
                
        for pin in range (1,8):
            label = 'input' + str(pin)
            if parser.has_option ('pulsecount', label):                             
                self.pulsecountList[pin] = {'received': 0, 'sent': 0, 'lastreceived': self.TODAYNOW,'lastsent': self.TODAYNOW }
                self.pulsecountFound = True
                
        for pin in self.pulsecountList:
            self.loggingInfo ('Input #' + str(pin) + ' is a pulse counter')       
                
        return
        
    def checkTempHot(self):    	
        if self.TEMP_CUR > self.TEMP_MAX:
            self.loggingError ("RaspberryPI is going to shutdown. Temperature: " + str(self.TEMP_CUR) + ' C' )            
            self.shutdown()
        return
        
    def checkEmergencyRelayOff(self):
        if self.relayoffFound == False:
            return
        
        mustRelayOff = False
        for pin in range (1,8):
            if pin in self.relayoffList:
                valueCur = int(self.pfd.input_pins[pin - 1].value)
                if self.relayoffList[pin]['previous'] != valueCur:
                    if self.relayoffList[pin]['poweroffvalue'] == valueCur:
                        mustRelayOff = True
                    self.relayoffList[pin]['previous'] = valueCur               
        
        if mustRelayOff == False:
            return

        if int (self.pfd.output_port.value) == 0:
            return
  
        self.loggingInfo ("Emergency Relay off !!")    
        self.pfd.output_port.all_off()
        self.getPinValue() 
        self.EVENTOUTPUT += 1 
        return                     

    def loggingDebug(self,text): 
        if self.DEBUG==1:
            logging.info (text)
        return
        
    def loggingInfo(self,text):
        logging.info (text)
        return

    def loggingError(self,text):
        logging.error (text) 
        return   
          
    def sendMessage (self,message):                   
        try:
            sock = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )   
            sock.settimeout (2)
            sock.connect (( self.addressWrite, int(self.PortWrite) ))    
            sent = sock.send (message)
            if sent == 0:
                self.loggingDebug ("sendMessage. SendMessage failure") 
            sock.close()
            
        except socket.timeout:
            self.loggingError ('sendMessage. Socket timoeut')
        except socket.error:
            self.loggingError ('sendMessage. Socket error: ' + str(sys.exc_info()[1][0]) + ',' + str(sys.exc_info()[1][1] ))
        except Exception as e:
            logging.error ('sendMessage error: ' + str(e))
            pass  
        return 
    
    def sockServerClose (self):
        # I connect to my SocketServer. 
        # So, will unblock by socket.accept and detect TERMINATE=True        
        try:
            sock = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )   
            sock.settimeout (0.1)
            sock.connect (( self.localAddress, int(self.PortRead) ))    
            sent = sock.send ('<cmd>TERMINATE</cmd>')            
            sock.close()
            
        except socket.timeout:
            pass
        except socket.error:
            pass
        except Exception as e:            
            pass  
        return 
       
    def signal_term_handler(self,signalnum, frame):         
        if signalnum == signal.SIGINT:
            self.loggingInfo  ("Received Ctrl+C")
        elif signalnum == signal.SIGTERM:
            self.loggingInfo  ("Received SIGTERM (-" + str(signalnum) + ")")
        #elif signalnum == signal.SIGKILL:
        #    self.loggingInfo  ("Received SIGKILL (-" + str(signalnum) + ")")
        elif signalnum == signal.SIGHUP:
            self.loggingInfo  ("Received SIGHUP (-" + str(signalnum) + ")")         
        else:   
            self.loggingInfo  ("Received Signal #" + str(signalnum))
        self.TERMINATE = True          
        return               
    
    def killChildProc (self):
        self.loggingDebug ("killing child process. Parent pid = " + str(self.PIDThreadMain))  
        ps = subprocess.Popen(['ps', '-ef'], stdout=subprocess.PIPE).communicate()[0]
        processes = ps.split('\n')
        nfields = len(processes[0].split()) - 1
        for row in processes[1:]:
            try:
                pid       = int(row.split(None, nfields)[1])
                pidparent = int(row.split(None, nfields)[2])
                if pid == self.PIDThreadMain:
                    continue                 
                if pidparent == self.PIDThreadMain:
                    self.loggingDebug ("killing pid=: " + str(pid))   
                    os.kill(pid, 9)
            except Exception as e:            
                pass      

        #os.kill(pid, signal.SIGHUP)
        #self.PIDThreadMain
        self.loggingDebug ("Finish killing child process")  
        pass
                      
    def run(self):
       
        filedummy = ''
        self.currentfile = os.path.abspath(__file__)
        self.currentpath, filedummy = os.path.split(self.currentfile)
        self.currentparm = self.currentpath + '/' + 'indigopiface.conf'
        self.currentdir  = os.getcwd()        
              
        if self.DEBUG==1:
            logging.basicConfig(filename='/var/log/indigopiface.log',level=logging.DEBUG,format="%(asctime)s - %(levelname)s: %(message)s")
        else:
            logging.basicConfig(filename='/var/log/indigopiface.log',level=logging.INFO,format="%(asctime)s - %(levelname)s: %(message)s")
                

        self.loggingInfo  ("********************************************************")
        self.loggingInfo  ("IndigoPiFace daemon")
        self.loggingInfo  ("********************************************************")
        self.loggingInfo  ("Start up")
        self.loggingInfo  ('Current file  = "' + self.currentfile + '"')
        self.loggingInfo  ('Current parm  = "' + self.currentparm + '"')
        self.loggingInfo  ('Current working directory = "' + self.currentdir + '"')
        
        self.getParm()
        self.loggingInfo  ("Debug: " + str(self.DEBUG))
        self.loggingInfo  ("Max temperature: " + str(self.TEMP_MAX) + ' C')

        self.TODAYNOW = datetime.datetime.now()
        self.nextTimeSoc   = self.TODAYNOW
        self.nextTimeCheck = self.TODAYNOW
        
        self.PIDThreadMain = os.getpid()
        
        
        self.ThreadSock = threading.Thread (target=self.serverSock,   name='ThreadSock', args=(self.addressRead,self.PortRead))
        self.ThreadTemp = threading.Thread (target=self.computerTemp, name='ThreadTemp')
        self.ThreadCpu  = threading.Thread (target=self.computerCPU,  name='ThreadCpu')
        
               
        self.ThreadSock.setDaemon(True)
        self.ThreadTemp.setDaemon(True)
        self.ThreadCpu.setDaemon(True)
        
        self.ThreadSock.start()
        self.ThreadTemp.start()
        self.ThreadCpu.start()
        
        
        self.loggingInfo ("PID Main = " + str(self.PIDThreadMain))
        
        signal.signal(signal.SIGTERM, self.signal_term_handler)
        signal.signal(signal.SIGHUP , self.signal_term_handler)
        signal.signal(signal.SIGINT , self.signal_term_handler)

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("gmail.com",80))
        self.localAddress = s.getsockname()[0]
        s.close()
        self.loggingInfo ("Local address = " + str(self.localAddress))
   
        self.pfd = pfio.PiFaceDigital()
        self.loggingInfo ("PifaceDigitalIO started")     
               
        for pin in range(1,8):
            self.inputList[pin]['led'] = int(self.pfd.input_pins[pin - 1].value)
        
        # El listener de Piface provoca que se cree un nuevo proceso, el cual no permite cerrar bien el servicio.
        # En github esta la version 3.1.0 de PiFaceDigital. Pero no esta en el repositorio de Raspbian.
        # https://github.com/piface/pifacedigitalio/commit/deeca22c49acd1809bfaf565f3f3654a68f5e039
        
         
        self.listener = pfio.InputEventListener(self.pfd) #(self.pfd, daemon=True)
        self.listener.detector.daemon = True
        self.listener.dispatcher.daemon = True
        for i in range(8):
            self.listener.register(i,pfio.IODIR_BOTH,self.eventInputProcess)            
        self.listener.activate()
         
        self.loggingInfo ("Event Listener started")
        self.loggingInfo ("********************************************************")

        self.getPinValue()        
        self.REQUESTSTATUS = True
        
        while True:
            if self.TERMINATE:
                break
            readPin   = False
            sockSend  = False  
            someCheck = False       

            self.TODAYNOW = datetime.datetime.now()
            
            if self.nextTimeCheck <= self.TODAYNOW:
                someCheck = True    
                
            if someCheck:
                self.nextTimeCheck = self.TODAYNOW + datetime.timedelta(seconds=self.IntervalCheck)
                self.checkTempHot()
                self.checkSleepCounters()
            
            if self.EVENTINPUT > 0:
                self.EVENTINPUT -= 1
                if self.EVENTINPUT < 0:
                    self.EVENTINPUT = 0
                sockSend = True
                readPin = True
                self.checkEmergencyRelayOff()
                self.loggingDebug ("Envio socket por cambio en los input")
               
            if self.EVENTOUTPUT > 0:
                self.EVENTOUTPUT -= 1
                if self.EVENTOUTPUT < 0:
                    self.EVENTOUTPUT = 0
                sockSend = True
                readPin = True
                self.loggingDebug ("Envio socket por cambio en los output")

            if self.REQUESTSTATUS:
            	self.REQUESTSTATUS = False
                readPin = True
                sockSend = True
                self.loggingDebug ("Envio socket por request status")
                              
            if self.nextTimeSoc <= self.TODAYNOW:
                readPin = True
                sockSend = True   
                 
            if readPin:
            	self.getPinValue()    

            if sockSend:    
                message = ''
                message = message + '<cpu>'  + str(self.CPU_USAGE)   + '</cpu>'
                message = message + '<temp>' + str(self.TEMP_CUR)    + '</temp>'
                message = message + '<in>'   + self.PIN_INPUT  + '</in>'
                message = message + '<out>'  + self.PIN_OUTPUT + '</out>'
                if self.pulsecountFound:
                    for pin in self.pulsecountList:
                        received = self.pulsecountList[pin]['received']
                        sent = self.pulsecountList[pin]['sent']
                        value = received - sent                        
                        if value > 0:
                            self.pulsecountList[pin]['sent'] = received
                            self.pulsecountList[pin]['lastsent'] = self.TODAYNOW
                            message = message + '<pulse' + str(pin) +'>' + str(value) + '</pulse' + str(pin) +'>'    
                self.sendMessage (message)  
                self.nextTimeSoc = self.TODAYNOW + datetime.timedelta(seconds=self.IntervalSoc)

            time.sleep(0.05)      
        
        self.sockServerClose() 
        self.listener.deactivate()       
        self.pfd.deinit_board()
        self.killChildProc()
        
                
        self.loggingInfo ("Exiting main loop")       
        return
    
    def test(self):
        while True:
            time.sleep(1)    
            
#***************************
#  MAIN
#***************************

class MyDaemon(Daemon):
    def run(self):
       
        indigo = MainIndigo()
        indigo.run()
        #indigo.test()
        logging.info ("***********")
        logging.info ("TERMINATING")
        logging.info ("***********")
        sys.exit()
          
if __name__ == "__main__":
    runner = MyDaemon('/var/run/indigopiface.pid',verbose=1)
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            #runner.run()
            runner.start()

            sys.exit()
        elif 'stop' == sys.argv[1]:
            runner.stop()
        elif 'restart' == sys.argv[1]:
            runner.restart()
        else:
             print "Unknown command"
             sys.exit(2)
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart" % sys.argv[0]
        sys.exit(2)
