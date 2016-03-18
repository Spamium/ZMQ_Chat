# ZMQ_Chat

v1.0 - ASInt chat

Simple group chat powered by ZMQ, on a Redis db
Working on a localhost as of the presentation date for the Internet Network Architecture project


The architecture is based on a central control node managing various chat servers.
Each chat server is independent and may manage various rooms at the same time.
Clients are only aware of the existance of the controller node and the chat rooms present on the network.

Servers and clients must know the IP of the controller, defaults to "localhost:13031"


controller.py:
Main controller script to be ran on a stable server. There are no recovery measures as of version 1.0
The controller is responsible for managing the heartbeats of every chat server in the network, adding and
removing servers as requested or as servers drop.
Server must have a static IP address reachable by the clients.

server.py:
Server script to be ran on a stable chat server.
The server is responsible for distributing the messages for all clients through a ZMQ publish socket, and
managing the heartbeats of every client on a room it has been assigned.
Room management is dynamically started as the controller directs new clients to the server.
If all clients drop from a room it is automatically closed.
Server must have a static IP address reachable by clients. The IP address is automatically sent the chosen
controller at start.

client.py:
Client script.
Simple text based chat window featuring room discovery. Non scrollable.
