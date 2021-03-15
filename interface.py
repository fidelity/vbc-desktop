#!/usr/bin/env python3.8
# Copyright 2021 FMR LLC <opensource@fidelity.com>
# SPDX-License-Identifer: MITB

"""CLI for the VBC CI"""

from messageHandler import *

#N second timeout for reading over serial
TIMEOUT = 2

#flag to delete contents of csv file upon script completion
DELETE_ON_STOP = True

#list of available commands
COMMANDS = '[init, fund, vault, unvault, spend, clawback, stop, help]'

#initial prompt
print('Pass a command from list of supported commands.\n'+COMMANDS)

# help messages for CLI
def vault_help_msg(has_args):
	if has_args:
		print("Unrecognized vault flag. List of available flags are:")
	else:
		print("Please specify a relative locktime, in blocks, for this vaulting.")
		print("Followed by a flag:")
	print("-a: Vault all deposited funds")
	print("-r: Unvault a random deposited outpoint")
	print("-l: Vault a list of specific txids")
	setDepositOutpoints()
	print("Can vault these TXs:")
	print(getDepositOutpoints())
def unvault_help_msg():
    print("Unrecognized unvault flag. List of available flags are:")
    print("-a: Unvault all funds")
    print("-l: Unvault list of specific txids")
    print("Can unvault these TXs:")
    print(getDiskTxids('vaulted'))

while True:
	command = input(">  ")

	command = command.split()

	# no args
	if len(command) == 1:
		command = command[0]
		#spins up regtest server
		if command == 'init':
			ignition()
		#printing a help message
		elif command == 'help':
			print('Pass a command from list of supported commands.\n'+COMMANDS)
		#stops application and cleans up
		elif command == 'stop':
			stop_nodes()
			close_port()
			if DELETE_ON_STOP:
				reset_txs()
			break
		elif command == 'quit':
			stop_nodes()
			close_port()
			break
		#simulates timelock by mining the necessary	amount of blocks
		elif command == 'simulate_timelock':
			print("-----------------------------------------------------", getTimelock(), "blocks later")
			generate(getTimelock())
		#mines a block and confirms the transaction in the mempool
		elif command == 'mine_block':
			generate(1)
		#makes sure bitcoind is running in the background
		elif command == 'test_bitcoind':
			jprint(bitcoinrpc('getblockchaininfo'))
		elif command == 'fund':
			print("Please pass an input value along with the fund command.")
			print("Or deposit bitcoin to this address to be available for vaulting:")
			print(getActiveAddress())
			bitcoinrpc('importaddress "'+getActiveAddress()+'"')
			#confirm any outstanding funding transactions
			generate(1)
			# Feedback on candidates for vaulting
			setDepositOutpoints()
			print("Have these funding outpoints:")
			print(getDepositOutpoints())
			continue
		elif command == 'vault':
			vault_help_msg(False)
			continue
		elif command == 'unvault':
			unvault_help_msg()
			continue
		elif command == 'spend':
			print("Please pass an address along with the spend command.")
			print("can spend these unvaulted TXs:")
			for txid, timelock in getSpendableTXs():
				confs = getconfirmations(txid)
				if int(timelock) <= confs:
					print(txid, timelock, "spendable")
				else:
					print(txid, int(timelock)-confs, "blocks left")
			continue
		elif command == 'clawback':
			print("Please pass an address along with the clawback command.")
			print("can clawback these unvaulted TXs:")
			print(getClawbackableTXs())
			continue
	elif len(command) == 2 and command[0] == 'clean':
		if command[1] == 'txs':
			reset_txs()
		elif command[1] == 'all':
			reset_regtest()
	#mines a block and confirms the transaction in the mempool
	elif len(command) == 2 and command[0] == 'mine_block':
		generate(command[1])
	#creates and confirms a funding transaction
	elif len(command) == 2 and command[0] == 'fund':
		# Import our funding address as watch-only
		bitcoinrpc('importaddress ' + str(getActiveAddress()))
		funding_txid = bitcoinrpc('sendtoaddress ' + str(getActiveAddress()) + ' ' + str(command[1]))
		print("Created Funding Input:\t", funding_txid)
		#confirming the funding transaction
		generate(1)
		# Feedback on candidates for vaulting
		setDepositOutpoints()
		print("Have these funding outpoints:")
		print(getDepositOutpoints())
	#initiates the 'normal spend' process, spending the P2TST through the OP_IF branch
	elif len(command) == 3 and command[0] == 'spend':
		# check 'spendability' of specified TX
		if command[2] in clawbacked_txs:
			print("Error. Funds have already been clawbacked.")
		elif command[2] in spent_txs:
			print("Error. Funds already spent.")
		else:
			print('initiating external spend process')
			# check txid validity + timelock condition
			txid_map = dict(getDiskTxids('unvaulted'))
			if command[2] in txid_map:
				if int(txid_map[command[2]]) <= int(getconfirmations(command[2])):
					setExternalAddress(command[1])
					createUnvaulChildTx(command[2], txid_map[command[2]])
					setSpent(command[2])
				else:
					print("Error. Timelock not expired.")
			else:
				print("Given txid not found as an unvaulted TX.")
	# initiates the emergency clawback process, spending the P2TST through the OP_ELSE branch
	elif len(command) == 3 and command[0] == 'clawback':
		print('initiating clawback process')
		txid_list = {value[0] for value in getClawbackableTXs()}
		# no checking against timelock, but don't want to rebroadcast
		if command[2] in txid_list:
			setRecoveryAddress(command[1])
			createUnvaulChildTx(command[2])
			setClawbacked(command[2])
		else:
			print("TX already clawbacked or invalid")
	# initiates the vaulting process and deposits funds into the vault
	elif len(command) >= 3 and command[0] == 'vault':
		if int(command[1]) >= 65536 or int(command[1]) <= 0:
			print("Invalid locktime. Must be between 1 and 65535, inclusive.")
			continue
		#first preparing the vault and sending message to board
		signThis = prepareVault()
		print("Preparing Vault")
		print("Sending random authenticated message string:\t", signThis)
		pack_data([signThis], 0)

		# rescan deposit outpoints
		setDepositOutpoints()

		# store the specified timelock
		setTimelock(command[1])
		applyTimelock(getTimelock())
		vaulting_txids = set()
		if command[2] == '-a':
			vaulting_txids = getDepositTxids()
		elif command[2] == '-r':
			random_txid = getDepositOutpoints().pop()
			vaulting_txids = {random_txid[0]}
		elif command[2] == '-l':
			requested_txids = set(command[3:])
			vaulting_txids = getDepositTxids()
			if len(requested_txids - vaulting_txids) != 0:
				print("Below txids not found:")
				print(requested_txids - vaulting_txids)
				continue
			vaulting_txids = requested_txids
		else:
			vault_help_msg(True)
			continue

		setVaultingOutpoints(vaulting_txids)
		print("UTXOs to be vaulted:")
		print(getVaultingOutpoints())
		time.sleep(TIMEOUT)

		#FIXME: do async comms!
		#reading the serial port and finalizing vault
		read_data()
		time.sleep(TIMEOUT)
		read_data()

	#initiates the unvaulting/process
	#can either pass amount, list of txids
	# TODO: remove unvaulted TXIDs from transactions.csv and related structures
	elif len(command) >= 2 and command[0] == 'unvault':
		txid_list = list()
		pure_txid_list = list()

		if command[1] == '-l':
			txid_list = unvault("-l", command[2:])
			pure_txid_list = {value[0] for value in txid_list}
			if pure_txid_list != set(command[2:]):
				print("Below txids not found.")
				print(set(command[2:]) - pure_txid_list)
				continue
			pure_txid_list = list(pure_txid_list)
		elif command[1] == '-a':
			txid_list = unvault("-a")
			if txid_list == -1:
				print("No txids vaulted.")
				continue
			pure_txid_list = [value[0] for value in txid_list]
		else:
			unvault_help_msg()
			continue

		print("sending list of txids:\t", txid_list)
		pack_data(pure_txid_list, 4)
		time.sleep(TIMEOUT*1.5)

		#FIXME: do async comms!
		read_data()
		#sending the txid_list back to board to delete them
		pack_data(pure_txid_list, 6)
		time.sleep(TIMEOUT)
		read_data()
		# record which TXs were unvaulted
		with open('unvaulted.csv', 'a') as fo:
			for txid in txid_list:
				fo.write(txid[0]+','+txid[1]+'\n')

	else:
		print('invalid command passed. please pass from list of supported commands.\n'+COMMANDS)
