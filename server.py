#!/usr/bin/env python

from urllib2 import urlopen
import zmq
from zmq.utils.monitor import recv_monitor_message
import random
import signal
import sys
import time
import datetime
import string
import redis
import threading
import pickle
from enum import IntEnum
import argparse

__author__ = "Hugeeks"
__credits__ = ["Hugeeks, Joao Pacheco"]
__version__ = "1.0.0"
__maintainer__ = "Hugeeks"
__email__ = "hugo00pereira@gmail.com"
__status__ = "Prototype"

parser = argparse.ArgumentParser()
parser.add_argument("-m","--mainserver", help="location of the controller server. Expects ipv4ADDR:port", default="localhost:13031")
parser.add_argument("-r","--replyport", help="custom port for replies", type=int, default=6000)
parser.add_argument("-p","--pubport", help="custom port for publishing", type=int, default=6001)
args = parser.parse_args()
if args:
	try:
		(mainIP, mainPort) = args.mainserver.split(":")
	except Exception:
		mainPort = "13031"
		mainIP = "localhost"
	
	repPort = args.replyport
	pubPort = args.pubport

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
myIP = urlopen('http://ip.42.pl/raw').read()
# myIP = "localhost" <---- or local IP

class heart(IntEnum):
	maxHP = 10
	timer = 1

class ops(IntEnum):
	greet = 0
	tell = 1
	leave = 2
	heartbeat = 5
	clear = 10
	
class tipe(IntEnum):
	text=0
	sys=1




database = redis.StrictRedis()


class server(object):
	
	def __init__(self, mainPort):
		self.live = True
		self.ekgList = []
		self.ekgMachines = []
		
		self.ctx = zmq.Context()
		
		self.mainSocket = self.ctx.socket(zmq.REQ)
		try:
			self.mainSocket.connect("tcp://%s:%d" % (mainIP, int(mainPort)))
		except Exception:
			print "Couldn't connect to main server\n\t%s" % Exception
			exit(-1)


	def register(self, repPort, pubPort):
		self.repSocket = self.ctx.socket(zmq.REP)
		self.pubSocket = self.ctx.socket(zmq.PUB)
		
		while True:
			if pubPort >65535:
				print "No port left for pubScoket"
				quit(-1)
			try:
				self.pubSocket.bind("tcp://*:%d" % pubPort)
				break
			# TODO expand exception
			except Exception:
				pubPort+=1
				
		while True:
			if repPort >65535:
				print "No port left for repSocket"
				quit(-1)
			try:
				self.repSocket.bind("tcp://*:%d" % repPort)
				break
			# TODO expand exception
			except Exception as detail:
				repPort+=1
		
		self.pubPort = pubPort
		self.repPort = repPort
		self.mainSocket.send("%d %s %d %d" % (ops.greet, myIP, pubPort, repPort))
		reply = self.mainSocket.recv()
		if reply == "OK":
			print "Registered with ports:\n\tPUB - %d\n\tREP - %d" % (pubPort, repPort)
		else:
			print "Could not register with main server:\n\t%s" % reply
			exit(-1)
	
	
	def listen(self):
		self.poller = zmq.Poller()
		self.poller.register(self.repSocket, zmq.POLLIN)
		print "Now listening"
		while self.live:
			if self.poller.poll(1000):
				incoming=self.repSocket.recv()
				parsed = incoming.split()
				
				if int(parsed[0]) == ops.greet:
					if not self.addUser(parsed):
						self.repSocket.send("User ID already exists")
					
				elif int(parsed[0]) == ops.tell:
					if self.spread(parsed):
						self.repSocket.send("OK")
					else:
						self.repSocket.send("NOK")
					
				elif int(parsed[0]) == ops.leave:
					self.removeUser(parsed)
					self.repSocket.send("OK")
					
				elif int(parsed[0]) == ops.heartbeat:
					self.repSocket.send("")
					self.recvHeartbeat(parsed)
			
			self.ekgMachineCheckUp()
	

	def addUser(self, parsed):
		parsed.pop(0)
		ID = parsed[0]
		alias = parsed[1]
		room = parsed[2]
		
		print "User '%s' looking for room '%s'" % (alias, room)
		targetRoom = "room %s" % room
		
		for i in range(0, database.llen(targetRoom)):
			data = pickle.loads(database.rpop(targetRoom))
			if ID in data:
				database.lpush(targetRoom, pickle.dumps(data))
				return False
			else:
				database.lpush(targetRoom, pickle.dumps(data))
		
		database.lpush(targetRoom, pickle.dumps([ID, alias, heart.maxHP]))
		print "\tsuccessfully connected!"
		print "Adding heartbeat monitor to room"
		if room not in self.ekgList:
			self.ekgList.append(room)
			print "\tcurrently we have:\n\t\t%s" % self.ekgList
			nthread = threading.Thread(target=server.startEKG, args=(self,room))
			self.ekgMachines.append(nthread)
			self.ekgMachines[len(self.ekgMachines)-1].start()
			print "\tThread started"
		
		self.repSocket.send("OK")
		time.sleep(0.1)
		self.updateUsers(room)
		return True
	
	
	def ekgMachineCheckUp(self):
		lista = self.ekgMachines
		for i in range(len(lista)):
			if not lista[i].isAlive():
				self.ekgMachines.pop(i)
	
	
	def spread(self, parsed):
		parsed.pop(0)
		room=parsed[0]
		alias=parsed[1]
		message=""
		for i in parsed[2:]:
			message+="%s "%i
		
		targetRoom = "room %s" % room
		llist = database.lrange(targetRoom, 0 ,-1)
		for i in llist:
			data = pickle.loads(i)
			if alias in data:
				seconds = time.time()
				timestamp = datetime.datetime.fromtimestamp(seconds).strftime('%H:%M')
				message = "[%s] <%s>: %s" % (timestamp, alias, message)
				self.pubSocket.send("%s %d %s" % (room, tipe.text, message))
				print "Sent message to all clients:\n\t%s %s" % (room, message)
				
				timestamp = datetime.datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')
				toDB = "%s - %s" % (timestamp, message)
				database.lpush("%s" % room, toDB)
				
				return True
			
		return False
	
	
	def updateUsers(self, room):
		targetRoom = "room %s" % room
		count = database.llen(targetRoom)
		self.pubSocket.send("%s %d %d" % (room, tipe.sys, count))
	
	def removeUser(self, parsed):
		parsed.pop(0)
		ID=parsed[0]
		room = parsed[1]
		targetRoom = "room %s" %room
		
		for i in range(0,database.llen(targetRoom)):
			data=pickle.loads(database.rpop(targetRoom))
			if ID in data:
				break
			else:
				database.lpush(targetRoom, pickle.dumps(data))
		
		if database.llen(targetRoom) == 0:
			self.signalClear(room)
			self.termEKG(room)
		else:
			self.updateUsers(room)
	
	
	def recvHeartbeat(self, parsed):
		parsed.pop(0)
		ID=parsed[0]
		room = parsed[1]
		targetRoom = "room %s" %room
		
		for i in range(0,database.llen(targetRoom)):
			data=pickle.loads(database.rpop(targetRoom))
			if ID in data:
				data[2]=heart.maxHP
				database.lpush(targetRoom, pickle.dumps(data))
				break
			else:
				database.lpush(targetRoom, pickle.dumps(data))
	
	
	def startEKG(self, room):
		targetRoom = "room %s" % room
		sig = False
		while room in self.ekgList:
			print "EKG for %s" % room
			length = database.llen(targetRoom)
			if(length==0):
				self.ekgList.remove(room)
				self.signalClear(room)
				break
				
			for i in range(0, length):
				data = pickle.loads(database.rpop(targetRoom))
				print "\t%s at %s" % (data[1], data[2])
				data[2] -= 1
				if(data[2] >= 0):
					database.lpush(targetRoom, pickle.dumps(data))
				else:
					sig = True
			if sig:
				sig=False
				self.updateUsers(room)
			time.sleep(heart.timer)
	
	
	def signalClear(self, room):
		self.mainSocket.send("%d %s" % (ops.clear, room))
		self.mainSocket.recv()
	
	
	def disconnect(self):
		print "Sent leave to server"
		self.mainSocket.send("%d %s %d" % (ops.leave, myIP,self.repPort))
		poller = zmq.Poller()
		poller.register(self.mainSocket, zmq.POLLIN)
		if poller.poll(1000):
			self.mainSocket.recv()
			print "Disconnected gracefully from master"
		else:
			print "No response from master server"
	
	def beatHeart(self):
		while self.live:
			self.mainSocket.send("%d %d" % (ops.heartbeat, self.pubPort))
			self.mainSocket.recv()
			
			time.sleep(random.random()*3)
	
	
	def termEKG(self, room):
		print "Spring cleaning on EKG list: %s" % self.ekgList
		for i in range(len(self.ekgList)):
			if room in self.ekgList[i]:
				print "\tpopped %s" % i
				self.ekgList.pop(i)
	
	
	def terminate(self):
		self.disconnect()
		self.live = False
		self.ekgList = []
		print "All cleaned up, waiting on something..."


# catching SIGINT
def signal_handler(signal, frame):
	print "\nSIGINT received\n\tsaying our final prayers" 
	if listener is not None:
		listener.terminate()
	print "Goodbye!"
	sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

listener=server(mainPort)
listener.register(repPort, pubPort)

listenThread = threading.Thread(target=listener.listen, args=())
heartThread = threading.Thread(target=listener.beatHeart, args=())
heartThread.start()
listenThread.start()
		
while True:	
	userIn = raw_input("")
	if userIn == "quit":
		listener.terminate()
		print "Goodbye!"
		quit()
		
		
