#!/usr/bin/env python

from urllib2 import urlopen
import socket
import zmq
print "Generating Big Bang"
import time
import redis
import threading
import pickle
import signal
import sys
from enum import IntEnum
import argparse

__author__ = "Hugeeks"
__credits__ = ["Hugeeks, Joao Pacheco"]
__version__ = "1.0.0"
__maintainer__ = "Hugeeks"
__email__ = "hugo00pereira@gmail.com"
__status__ = "Prototype"



parser = argparse.ArgumentParser()
parser.add_argument("-m","--mainport", help="custom port for the server", type=int, default=13031)
args = parser.parse_args()
if args:
	mainPort = args.mainport
	
print mainPort

class ops(IntEnum):
	greet = 0
	leave = 2
	listR = 3
	lookupR = 4
	heartbeat = 5
	clear = 10
	
class heart(IntEnum):
	maxHP = 10
	timer = 1

database = redis.StrictRedis()

class controller(object):
	
	def __init__(self, mainPort):
		self.live = True
		
		self.ctx = zmq.Context()
		self.socketIn = self.ctx.socket(zmq.REP)
		self.socketIn.bind("tcp://*:%s" % mainPort)
		print "Initialized socket on : %d" % mainPort
		
		self.poller = zmq.Poller()
		self.poller.register(self.socketIn, zmq.POLLIN)
	
	
	def listen(self):
		print "\tThread listening"
		while self.live:
			if self.poller.poll(1000):
				incoming=self.socketIn.recv()
				parsed = incoming.split()
				
				if int(parsed[0]) == ops.greet:
					# Server greeting
					if self.addServer(parsed):
						self.socketIn.send("OK")
					else:
						self.socketIn.send("NOK")
										
				elif int(parsed[0]) == ops.leave:
					# Server leaving
					self.remServer(parsed)
					
				elif int(parsed[0]) == ops.listR:
					# Client requested room list
					self.sendList()
					
				elif int(parsed[0]) == ops.lookupR:
					# Client requested room ports
					self.sendPorts(parsed)

				elif int(parsed[0]) == ops.heartbeat:
					# Server heartbeat
					self.recvHeartbeat(parsed)
					
				elif int(parsed[0]) == ops.clear:
					# Server notifying room is empty
					self.socketIn.send("")
					self.clear(parsed)
	

	def addServer(self, parsed):
		# Parsed - [ops.greet, ip, repPort, pubPort]
		parsed.pop(0)
		print "Adding a new server at %s:(%s, %s)" % (parsed[0], parsed[1], parsed[2])
		server = [(parsed[0], int(parsed[1]), int(parsed[2])), 0, heart.maxHP]
		database.lpush("serv servers", pickle.dumps( server ))
		
		return True
	

	def sendPorts(self, parsed):
		# Parsed - [ops.join, room]
		parsed.pop(0)
		
		print "Looking for room - '%s'" % parsed[0]
		print database.llen("serv rooms")
		for i in range(0,database.llen("serv rooms")):
			data = pickle.loads(database.lindex("serv rooms", i))
			if parsed[0] in data:
				print "\tfound room at %s:(%d, %d)" % (data[1][0], data[1][1], data[1][2])
				self.socketIn.send("%s %d %d" % (data[1][0], data[1][1], data[1][2]))
				return True
				
		print "Iterating servers for suitable room controller"
		minOpen = float('inf')
		holder = None
		for i in range(database.llen("serv servers")):
			data = pickle.loads(database.rpop("serv servers"))
			if data[1] < minOpen:
				minOpen = data[1]
				if holder:
					database.lpush("serv servers", pickle.dumps(holder))
				holder = data
			else:
				database.lpush("serv servers", pickle.dumps(data))
		
		if minOpen == float('inf'):
			self.socketIn.send("No servers available")
			print "No socket availabe to hold new room"
			
		else:
			# Send server data back to DB with incremented number of rooms
			database.lpush("serv servers", pickle.dumps([holder[0], holder[1]+1, holder[2]]))
			database.lpush("serv rooms", pickle.dumps([parsed[0], holder[0]]))
			
			# Send holder[0]: (ip, portRep, portPub) [REQUIRES CONFIRMATION ON PORT ORDER]
			self.socketIn.send("%s %d %d" % (holder[0][0], holder[0][1], holder[0][2]))
			print "Sending the location of room '%s' - %s:(%d, %d)" % (parsed[0], holder[0][0], holder[0][1], holder[0][2])
		
		
	
	
	def remServer(self, parsed):
		# Parsed = [ops.leave, ip, port]
		parsed.pop(0)
		
		print "Trying to remove server at %s" % parsed[0]
		for i in range(database.llen("serv servers")):
			data = pickle.loads(database.rpop("serv servers"))
			if parsed[0] not in data[0] and parsed[1] not in data[0]:
				database.lpush("serv servers", pickle.dumps(data))
			else:
				print "\tserver successfully removed"
				break
		
		self.socketIn.send("")
		
		for i in range(database.llen("serv rooms")):
			data = pickle.loads(database.rpop("serv rooms"))
			if parsed[0] not in data[1]:
				database.lpush("serv rooms", pickle.dumps(data))
			else:
				ports = data[1]
		
		# [MARKED FOR REVIEW, USELESS HERE, USE FOR CLEAN ROOM]
		#
		#for i in range(database.llen("serv servers")):
		#	data = pickle.loads(database.rpop("serv servers"))
		#	if ports in data:
		#		database.lpush("serv servers", pickle.dumps([data[0], data[1]-1, data[2]]))
	
	
	def sendList(self):
		message = ""
		data = database.lrange("serv rooms", 0, -1)
		
		for i in data:
			message += "%s " % pickle.loads(i)[0] 
		
		self.socketIn.send(message)
		
		
	def recvHeartbeat(self, parsed):
		# Parsed - [ops.heartbeat, ip]
		parsed.pop(0)
		
		for i in range(database.llen("serv servers")):
			data = pickle.loads(database.rpop("serv servers"))
			if int(parsed[0]) in data[0]:
				data[2]=heart.maxHP
			database.lpush("serv servers", pickle.dumps(data))
		
		self.socketIn.send("")
		
					
	def heartTicker(self):
		while self.live:
			for i in range(database.llen("serv servers")):
				element=database.rpop("serv servers")
				if element:
					data = pickle.loads(element)
				else:
					break
					
				data[2] -= 1
				if data[2]>=0:
					database.lpush("serv servers", pickle.dumps(data))
			
			time.sleep(heart.timer)
					
					
	def clear(self, parsed):
		# Parsed - [ops.clear, room]
		parsed.pop(0)
		
		for i in range(database.llen("serv rooms")):
			data = pickle.loads(database.rpop("serv rooms"))
			if parsed[0] not in data:
				database.lpush("serv rooms", pickle.dumps(data))
			else:
				target = data[1]
				for i in range(database.llen("serv servers")):
					data = pickle.loads(database.rpop("serv servers"))
					if target in data:
						data[1] -= 1
						database.lpush("serv servers", pickle.dumps(data))
						return True
					database.lpush("serv servers", pickle.dumps(data))  
				

	def terminate(self):
		self.live = False


def signal_handler(signal, frame):
	print "\nSIGINT received\n\tsaying our final prayers" 
	ctrl.terminate()
	print "Goodbye!"
	sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

ctrl=controller(mainPort)

listeningThread=threading.Thread(target=ctrl.listen, args=())
heartbeatThread = threading.Thread(target=ctrl.heartTicker, args=())
listeningThread.start()
heartbeatThread.start()


while True:
	
	com = raw_input("")
	if com == "quit":
		ctrl.terminate()
		print "Goodbye!"
		quit()	


