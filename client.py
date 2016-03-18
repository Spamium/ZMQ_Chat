#!/usr/bin/env python

import os
import signal
import random
from enum import IntEnum
import sys
import zmq
from zmq.utils.monitor import recv_monitor_message
import time
import threading
import string
import argparse

__author__ = "Hugeeks"
__credits__ = ["Hugeeks, Joao Pacheco"]
__version__ = "1.0.0"
__maintainer__ = "Hugeeks"
__email__ = "hugo00pereira@gmail.com"
__status__ = "Prototype"


## MONITOR
## https://github.com/zeromq/pyzmq/blob/master/examples/monitoring/simple_monitor.py
##EXPERIMENTAL
EVENT_MAP = {}
print("Event names:")
for name in dir(zmq):
	if name.startswith('EVENT_'):
		value = getattr(zmq, name)
		#print("%21s : %4i" % (name, value))
		EVENT_MAP[value] = name
		


#monitor = socketIn.get_monitor_socket()

#expt = threading.Thread(target=event_monitor, args=(monitor,))
#expt.start()
##EXPERIMENTAL


parser = argparse.ArgumentParser()
parser.add_argument("-m","--mainserver", help="location of the controller server. Expects ipv4ADDR:port", default="localhost:13031")
args = parser.parse_args()
if args:
	try:
		(mainIP, mainPort) = args.mainserver.split(":")
	except Exception:
		mainPort = "13031"
		mainIP = "localhost"


class ops(IntEnum):
	greet = 0
	tell = 1
	leave = 2
	listR = 3
	lookupR = 4
	heartbeat = 5

class tipe(IntEnum):
	text = 0
	sys = 1


class client(object):
	
	def __init__(self, mainPort):
		self.alias = "Anonymous"
		self.ID = int(random.random()*10000+random.random()*1000+random.random()*100+random.random()*10+random.random())
		self.connected = False
		self.helpF = False
		
		self.printMessage=""
		self.lineHistory = []
		self.lineMax = 14
		self.room = None
		self.users = "0"
		self.cursor=">"
		
		self.alias = None
		self.live = True
		self.listenLive = False
		self.heartLive = False
		self.subPort = -1
		
		self.ctx = zmq.Context()
		self.mainSocket = self.ctx.socket(zmq.REQ)
		
		self.poller = zmq.Poller()
		self.serverpoller = zmq.Poller()
		
		
		try:
			self.mainSocket.connect("tcp://%s:%s" % (mainIP, mainPort))
		except Exception:
			print "Couldn't connect to main server\n\t%s" % Exception
			quit(-1)
			
		
	def listRooms(self):
		self.mainSocket.send("%d" % ops.listR)
		self.printMessage = self.mainSocket.recv()
		
		
	def askPorts(self, room):
		print "Asking main server for the room"
		self.mainSocket.send("%d %s" % (ops.lookupR, room))
		ports = self.mainSocket.recv()
		if ports == "NOK":
			return False
		
		self.serverSocket = self.ctx.socket(zmq.REQ)
		self.subSocket = self.ctx.socket(zmq.SUB)
		
		ports = ports.split()
		print "\tturning ports into connections\n\t\tREP - %s\n\t\tSUB - %s" % (ports[2], ports[1])
		try:
			self.serverSocket.connect("tcp://%s:%s" % (ports[0], ports[2]))
			self.subPort = ports[1]
		except Exception:
			print "Could not connect to server socket at %s:%s > \n\t%s" % (ports[0], ports[2], Exception)
			return False
			
		try:
			self.subSocket.connect("tcp://%s:%s" % (ports[0], ports[1]))
		except Exception:
			print "Could not connect to publisher socket at %s:%s > \n\t%s" % (ports[0], ports[1], Exception)
			return False
		
		self.poller.register(self.subSocket, zmq.POLLIN)
		self.serverpoller.register(self.serverSocket, zmq.POLLIN)
		
		return True
	
	
	def register(self):
		print "Greeting server"
		self.serverSocket.send("%d %d %s %s" % (ops.greet, self.ID, self.alias, self.room))
		if self.serverpoller.poll(5000):
			resp = self.serverSocket.recv()
		else:
			print "Server did not respond"
			return False
			
		if resp == "OK":
			print "\tserver pong'd"
			return True
		else:
			print "\tserver said: %s" % resp
			return False
	
	
	def joinRoom(self, room):
		if self.askPorts(room):
			self.room = room
			self.cursor = "%s>" % self.alias
			if self.register():
				self.connected = True
				self.listenLive = True
				self.heartLive = True
				
				self.listening = threading.Thread(target=client.listen, args=(self, "%s" % room))
				self.listening.start()
				self.heart = threading.Thread(target=self.beatHeart, args=())
				self.heart.start()
				
				return True
		else:
			self.room = None
			return False	
		
		
	def tell(self, messageL):
		message=""
		for i in messageL:
			message += "%s " % i
		self.serverSocket.send("%d %s %s %s" % (ops.tell, self.room, self.alias, message))
		
		if self.serverpoller.poll(5000):
			if self.serverSocket.recv()!="OK":
				print "We were disconnected from the chat room: %s" % self.room
				self.leaveRoom()
		else:
			print "Server did not respond"


	def leaveRoom(self):
		count = 0
		print "Attempting to leave room %s" % self.room
		self.listenLive = False
		while self.listening.isAlive():
			_=0
		
		self.serverSocket.send("%d %d %s" % (ops.leave, self.ID, self.room))
		while True:
			if self.serverpoller.poll(1000):
				if self.serverSocket.recv() == "OK":
					break
			else:
				print "Server did not respond"
				
			count+=1
			if count is 6:
				return False
					
			time.sleep(1)
			print "\tRetrying (%d)..." % count
		
		self.subSocket.close()
		self.serverSocket.close()
		self.leaveTerm()
		self.room = None
		self.cursor = ">"
		self.connected = False
		self.lineHistory=[]
		
		return True


	def listen(self, room):
		self.subSocket.setsockopt(zmq.SUBSCRIBE, "%s" % room)
		while self.listenLive:
			if self.poller.poll(1000):
				message = self.subSocket.recv()
				_,tipo, message = message.split(" ",2)
				if int(tipo) == tipe.text:
					self.lineHistory.append(message)
					if len(self.lineHistory) > self.lineMax:
						self.lineHistory.pop(0)
					printOut(self)
				elif int(tipo)==tipe.sys:
					self.users = message
					printOut(self)


	def beatHeart(self):
		while self.heartLive:
			self.serverSocket.send("%d %d %s" % (ops.heartbeat, self.ID, self.room))
			
			if self.serverpoller.poll(1000):
				self.serverSocket.recv()
			else:
				print "Server did not respond"
			
			time.sleep( random.random()*3 )


	def leaveTerm(self):
		self.heartLive = False
		self.listenLive = False


	def terminate(self):
		print "Terminating listener"
		self.heartLive = False
		self.listenLive = False
		self.live = False


def printOut(listener):
	if not listener.connected:
		print "\033cWelcome to the ASInt Chat, %s\n\n" % listener.alias
		print "You are not connected to a room"
		print "\n"*5
		print "%s" % listener.printMessage
		listener.printMessage = ""
		print "\n"*9
		
	else:
		sys.stdout.write("\033c")
		print "/" + ("-" * (len("Room: %s (%s)" % (listener.room, listener.users))+2))+"\\"
		print "| Room: %s (%s) |" % (listener.room, listener.users)
		print "\\" + ("-" * (len("Room: %s (%s)" % (listener.room, listener.users))+2))+"/"
		print ""
		for i in listener.lineHistory:
			print i
		print "\n"*(listener.lineMax-len(listener.lineHistory)+1)
	sys.stdout.write(listener.cursor)
	sys.stdout.flush()

# Event monitor method
def event_monitor(monitor):
	while monitor.poll():
		evt = recv_monitor_message(monitor)
		evt.update({'description': EVENT_MAP[evt['event']]})
		print("Event: {}".format(evt))
		if evt['event'] == zmq.EVENT_MONITOR_STOPPED:
			break
	monitor.close()
	print()
	print("event monitor thread done!")


# catching SIGINT
def signal_handler(signal, frame):
	print "\nSIGINT received\n\tsaying our final prayers" 
	if listener is not None:
		listener.terminate()
	sys.stdout.write("\033c")
	sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

listener = client(mainPort)

alias = raw_input("\033cWelcome to ASInt Chat\n\nType your desired alias for this session:\t")
listener.alias = alias.split()[0]

while True:
	printOut(listener)
	userIn = raw_input()
	if userIn:
		parsed = userIn.split()
		
		if parsed and parsed[0][0] == "/":
			if parsed[0][1:] == "list" and not listener.connected:
				listener.listRooms()
				
			elif parsed[0][1:] == "join" and not listener.connected:
				if listener.joinRoom(parsed[1]):
					print "Now connected to room %s" % listener.room
				else:
					print "Could not connect to %s" % listener.room
				
			elif parsed[0][1:] == "leave" and listener.connected:
				if not listener.leaveRoom():
					print "Could not leave room %s\n\tTry again later or restart chat client" % listener.room
					
			elif parsed[0][1:] == "quit":
				if listener.connected:
					listener.leaveRoom()
			
				print "Shutting Down" 
				if listener is not None:
					listener.terminate()
				
				sys.stdout.write("\033c")
				quit(0)
			
			elif parsed[0][1:] == "help":
				listener.printMessage = "'/list' to list rooms\t'/join [room]' to connect\t'/quit' to exit"
				
			else:
				print "Command %s not accepted or recognized" % parsed[0]
		
		elif listener.connected:
			listener.tell(parsed)
