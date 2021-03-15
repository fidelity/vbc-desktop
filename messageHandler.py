# Copyright 2021 FMR LLC <opensource@fidelity.com>
# SPDX-License-Identifer: MIT

'''
#FIXME: add the message Ids into a dictionary
Message IDs: Corresponding Messages
0			: PrepareVault(signThis) - computer sends, board receives
1			: PrepareVaultResponse(Address, sig(signThis)) - board sends, computer receives
2			: FinalizeVault(unsigned P2TST)	- computer sends, board receives
3			: FinalizeVaultResponse(txid, isDeleted) - board sends, computer receives
4			: UnvaultRequest([txid_list]) - computer sends, board recieves
5			: UnvaultResponse([p2tst_list]) - board sends, computer receives

6			: ConfirmDelete([txid_list]) - computer sends, board receives
7			: ConfirmDeleteResponse() - board sends, computer receives
'''

from binascii import unhexlify
import serial
from transactionHandler import *

#divider between msg id and message
HEADER_CONSTANT	= '___'

#divider between each part of subsequent message fields
MSG_DIVIDER	= '##?'

ser = serial.Serial('/dev/tty.usbmodem335E375633382')
# simulator connection
# ser = serial.serial_for_url('socket://localhost:8789')
# ser.baudrate = 9600
# ser.timeout = 2

def serializeField(data):
	'''
	properly serializes data dependent on its data type
	'''
	if isinstance(data, bytes):
		return data
	elif isinstance(data, str):
		return bytes(data, 'utf8')
	elif (isinstance(data, int)) or (isinstance(data, bool)):
		return bytes([data])
	else:
		print('unrecgonized data type...')
		return False

def close_port():
	'''
	closes serial port upon application completion
	'''
	ser.close()

def read_data():
	'''
	reads the data in the serial port and sends it to be unpacked
	'''
	return unpack_data(ser.read_until())

def unpack_data(buffer):
	'''
	will unpack the data from serial part
	it will first extract the ID from the header, and will pass the rest of message to proper function
	'''
	#print("Received:\t", buffer)

	#unpacking message id in header
	decoded_msg = buffer.decode('utf8').split(HEADER_CONSTANT)
	msgId = int.from_bytes(bytes(decoded_msg[0], 'utf8'), 'big') #decode the msgId

	split_msg = decoded_msg[1].split(MSG_DIVIDER)
	split_msg = split_msg[:-1]

	if msgId == 1:
		prepareVaultResponse_handler(split_msg)
	elif msgId == 3:
		finalizeVaultResponse_handler(split_msg)
	elif msgId == 5:
		unvaultResponse_handler(split_msg)
	elif msgId == 7:
		confirmDeleteResponse_handler(split_msg)
	else:
		#FIXME: better error handling
		print("unidentified msg id")
		return 1
	return 0

def pack_data(msg, msgId):
	'''
	encapsulates and prepares the data to be sent to the board
	'''

	#preparing the message to send back to computer
	buffer = bytes([msgId]) + bytes(HEADER_CONSTANT, 'utf8')

	#need to split up data to differentiate objects in message
	for field in msg:
		buffer += serializeField(field)
		buffer += bytes(MSG_DIVIDER, 'utf8')

	buffer += bytes('\n', 'utf8')
	# print("Sent:\t", buffer)

	#tacking on the message to be sent over serial
	return send_data(buffer)

def send_data(buffer):
	'''
	writes data in buffer to  serial port
	'''
	ser.write(buffer)
	return 0

def prepareVaultResponse_handler(buffer):
	'''
	receives the vault wallet ddress and signature(signThis) from board

	will verify signature then finalize vault
	'''
	addr = buffer[0]
	sig = buffer[1]

	print("Receieved address:\t", addr)
	print("Received authenticated message signature:\t", sig)

	#if the message was not authenticated, stop everything!
	if not isAuthenticatedMessage(unhexlify(sig)):
		#FIXME: better error handling
		print("Unauthenticated Message. Stop everything!")
		return -1

	res = finalizeVault(addr)
	print("Sending unsigned transaction:\t", res)
	return pack_data(res, 2)

def finalizeVaultResponse_handler(buffer):
	'''
	receives confirmation of private key being deleted, along with P2TST txid and amount

	will add the txid and amount to the list of other vaulted P2TSTs
	'''
	isDeleted = buffer[0]
	returned_txids = list()
	returned_amounts = list()
	for index, value in enumerate(buffer[1:]):
		if index % 2 == 0:
			returned_txids.append(value)
		else:
			returned_amounts.append(value)

	print("Receieved presigned transaction txids:\t", returned_txids)
	print("Receieved presigned transaction amounts:\t", returned_amounts)

	#if the key was not deleted, stop everything!
	if not isDeleted:
		#FIXME: better error handling
		print("key not deleted. Stop everything!")
		return -1

	#saving the txid to a file
	with open("transactions.csv", 'a') as fo:
		for index, txid in enumerate(returned_txids):
			fo.write(txid+','+str(returned_amounts[index])+',vaulted,'+str(getTimelock())+'\n')

	# broadcast deposit transactions
	for hex_tx in getDepositTXs():
		bitcoinrpc('sendrawtransaction '+hex_tx)
	clearDepositTXs()
	generate(1)

def unvaultResponse_handler(buffer):
	'''
	receives a list of P2TST hexes from board

	will iterate through this list and broadcast each of them
	'''
	print("Received list of pre-signed transaction hex:\t", buffer)
	for tx in buffer:
		bitcoinrpc('sendrawtransaction ' + str(tx))
	generate(1) #confirming p2tsts


def confirmDeleteResponse_handler(buffer):
	print("transactions have been successfuly deleted on board.")
