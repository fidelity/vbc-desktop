# Copyright 2021 FMR LLC <opensource@fidelity.com>
# SPDX-License-Identifer: MIT

"""core logic for TX construction and bookkeeping"""

from random import choice
from string import ascii_lowercase
from helpers import *

FEE_AMOUNT = 0.002 #sample fee amount for regtest broadcasts

#test private keys
privkeys = {
    'active'    :  	makekey(b'active'), 	#send/receive funds to/from vault wallet
    'clawback'  :  	makekey(b'clawback'), 	#spends to recovery wallet
}

#correspodning test public keys
pubkeys = {x:privkeys[x].pub for x in privkeys}
pubkeys['vault'] = CPubKey(b'\x03\xb9\xffV\xfb\xf99v\xc6\xd4W\xf2F\x0b\x00\x00q\xdaD\xed\xcaf\x95\xae\x0bM\xd9\x97\x9dslv\x17') #the vault wallet device pubkey

# all outpoints owned by the active wallet
deposit_outpoints = set()
# subset of deposit_outpoints, set aside for vaulting
vaulting_outpoints = set()
# record clawbacked TXs
clawbacked_txs = set()
# record spent TXs
spent_txs = set()
# hex-encoded, signed deposit TXs, ready for broadcast
signed_deposit_txs = set()
# bech32 addresses provided by the user
user_addresses = {}
# shared storage for the P2TST script and associated relative timelock
scripts = {}
# global timelock value set by user
vault_timelock = 0
#FIXME: should be random
authenticated_string = ''

def setRecoveryAddress(addr):
	"""
	destination of clawback/emergency spend
	"""
	user_addresses['recovery'] = tobechaddress(str(addr))
def setExternalAddress(addr):
	"""
	destination of normal timelocked spend
	"""
	user_addresses['external'] = tobechaddress(str(addr))
def setTimelock(locktime):
	"""
	bounds check for user-provided timelock
	"""
	global vault_timelock
	if int(locktime) >= 65536 or int(locktime) <= 0:
		raise ValueError("Invalid relative locktime! Must be on [1, 65536)")
	vault_timelock = int(locktime)
def getTimelock():
	return int(vault_timelock)
def applyTimelock(timelock_int):
	"""
	generate P2TST script with timelock
	"""
	global scripts

	# timelock branch
	op_list = encodelocktime(timelock_int)
	op_list += [OP_NOP3, OP_DROP, pubkeys['active'], OP_CHECKSIG]
	# clawback branch
	op_list += [OP_ELSE, pubkeys['clawback'], OP_CHECKSIG, OP_ENDIF]
	script_list = CScript(op_list)
	scripts['p2tst'] = script_list
def getDepositTXs():
	return signed_deposit_txs
def clearDepositTXs():
	"""
	reset our store of TXs ready to be vaulted
	"""
	signed_deposit_txs.clear()
def setDepositOutpoints():
	"""
	Look up all outpoints controlled by the active wallet
	Returned as set of tuples (txid, index, value)
	"""
	global deposit_outpoints
	deposit_outpoints.clear()
	deposit_txs = bitcoinrpc('listunspent 0 9999999 '+'"[\\"'+getActiveAddress()+'\\"]"')
	deposit_outpoints = {(tx["txid"], tx["vout"], tx["amount"]) for tx in deposit_txs}
def getDepositOutpoints():
	return deposit_outpoints
def getDepositTxids():
	"""
	filter deposit outpoints to only return txids
	"""
	return {value[0] for value in getDepositOutpoints()}
def getSpendableTXs():
	return {pair for pair in getDiskTxids("unvaulted") if pair[0] not in clawbacked_txs and pair[0] not in spent_txs}
def getClawbackableTXs():
	return {pair for pair in getDiskTxids("unvaulted") if pair[0] not in clawbacked_txs}
def setSpent(txid):
	spent_txs.add(txid)
def setClawbacked(txid):
	clawbacked_txs.add(txid)
def setVaultingOutpoints(txids):
	"""
	Given a set of txids the active wallet owns
	store (txid, index, value) data and flag for vaulting
	"""
	global vaulting_outpoints
	vaulting_outpoints.clear()
	setDepositOutpoints()
	for utxo in getDepositOutpoints():
		if utxo[0] in txids:
			vaulting_outpoints.add(tuple(utxo))
def getVaultingOutpoints():
	return vaulting_outpoints
def getActiveAddress():
	"""
	returns the address correspdoning to the active wallet public key
	"""
	return str(P2PKHBitcoinAddress.from_pubkey(pubkeys['active']))
def setSignThis(m):
	global authenticated_string
	authenticated_string = m
def getSignThis():
	return authenticated_string
def generateSignThis(length):
	"""
	generates a random string to check for authenticated messages
	"""
	letters = ascii_lowercase
	return ''.join(choice(letters) for i in range(length))
def prepareVault():
	"""
	generates signThis to be sent to the board for authenticated message checking
	"""
	signThis = generateSignThis(32)
	setSignThis(signThis)
	return signThis
#FIXME: Implement authenticated message check
def isAuthenticatedMessage(sig):
	"""
	complete handshake with board
	"""
	msg_hash = getSignThis()
	print(msg_hash)
	return pubkeys['vault'].verify(bytes(msg_hash, 'utf8'), sig)
def createDepositTx(txid, vout, amount, fee, vault_address):
	"""
	Create a signed vaulting TX; standard P2SH
	Returns (hex-encoded tx, txid, value)
	"""
	amount -= fee
	deposit_txin = CMutableTxIn(COutPoint(lx(txid), vout))
	deposit_txin_scriptPubKey = CScript([OP_DUP, OP_HASH160, Hash160(pubkeys['active']), OP_EQUALVERIFY, OP_CHECKSIG])

	#spending to the vault wallet's address (the address of newly generated key)
	deposit_txout = CMutableTxOut(amount*COIN, CBitcoinAddress(str(vault_address)).to_scriptPubKey())

	#adding the inputs/outputs
	deposit_tx = CMutableTransaction([deposit_txin], [deposit_txout])

	#signing the inputs to be spent
	deposit_sighash = SignatureHash(deposit_txin_scriptPubKey, deposit_tx, 0, SIGHASH_ALL)
	deposit_sig = privkeys['active'].sign(deposit_sighash) + bytes([SIGHASH_ALL])
	deposit_txin.scriptSig = CScript([deposit_sig, pubkeys['active']])

	#verifying the signature worked and no issues at signing
	VerifyScript(deposit_txin.scriptSig, deposit_txin_scriptPubKey, deposit_tx, 0, (SCRIPT_VERIFY_P2SH,))

	#preparing the TxIn of the P2TST transaction
	deposit_tx_hex = b2x(deposit_tx.serialize())
	return (deposit_tx_hex, deposit_tx.GetTxid(), amount)
def finalizeVault(addr):
	"""
	finalizeVault will prepare both the vaulting transaction along with the unsigned p2tst
	the vaulting transaction will spend the funding UTXO created earlier
	the p2tst will spend the vaulting transaction to an OP_IF/OP_ELSE timelocked script
	"""
	vault_txs = list()
	for utxo in getVaultingOutpoints():
		# create deposit transaction input
		deposit_tx_hex, deposit_txid, deposit_amount = createDepositTx(utxo[0], utxo[1], utxo[2], FEE_AMOUNT, addr)
		vault_amount = deposit_amount - FEE_AMOUNT
		deposit_vout = 0
		p2tst_txin = CMutableTxIn(COutPoint(deposit_txid, deposit_vout))
		#spending to the OP_IF/OP_ELSE timelocked script found above
		p2tst_txout = CMutableTxOut(vault_amount*COIN, scripts['p2tst'].to_p2sh_scriptPubKey())
		#adding inputs/outputs and returning the serialized hex
		p2tst_tx = CMutableTransaction([p2tst_txin], [p2tst_txout])
		signed_deposit_txs.add(deposit_tx_hex)
		vault_txs.append(b2x(p2tst_tx.serialize()))

	return vault_txs
def unvault(flag, second_arg=None):
	"""
	open file with txids and amounts.
	append to list until amount is reached
	send txid list to board
	"""
	txid_list = list()

	if flag == '-l':
		requested_txids = second_arg
		vaulted_txs = getDiskTxids('vaulted')
		for tx_tuple in vaulted_txs:
			if tx_tuple[0] in requested_txids:
				txid_list.append(tx_tuple)
	elif flag == '-a':
		txid_list = getDiskTxids('vaulted')
		if len(txid_list) == 0:
			return -1

	return txid_list
def createUnvaulChildTx(txid, timelock=None):
	"""
	create a signed TX that spends an unvaulted TX
	Returns a signed TX
	"""
	clawing_back = timelock is None
	# parameters that differ between clawback and spend (not keys or addresses)
	# TODO: Dynamic fees
	unvault_nSequence = 0xffffffff if clawing_back else int(timelock)
	scriptsig_opcode = OP_FALSE if clawing_back else OP_TRUE
	fee = FEE_AMOUNT*2 if clawing_back else FEE_AMOUNT

	amount = bitcoinrpc('getrawtransaction ' + txid + ' true')['vout'][0]['value'] - fee

	# recreate vaulting script
	parent_locktime = getDiskLocktime(txid)
	applyTimelock(parent_locktime)
	p2tst_redeemScript = scripts['p2tst']
	p2tst_scriptPubKey = p2tst_redeemScript.to_p2sh_scriptPubKey()
	txin = CMutableTxIn(COutPoint(lx(txid), 0), nSequence=unvault_nSequence)
	txout = CMutableTxOut(amount*COIN, user_addresses['recovery'].to_scriptPubKey()) if clawing_back \
		else CMutableTxOut(amount*COIN, user_addresses['external'].to_scriptPubKey())

	full_tx = CMutableTransaction([txin], [txout], nVersion=2)
	sighash = SignatureHash(p2tst_redeemScript, full_tx, 0, SIGHASH_ALL)
	tx_sig = privkeys['clawback'].sign(sighash) + bytes([SIGHASH_ALL]) if clawing_back \
		else privkeys['active'].sign(sighash) + bytes([SIGHASH_ALL])
	txin.scriptSig = CScript([tx_sig, scriptsig_opcode, p2tst_redeemScript])

	VerifyScript(txin.scriptSig, p2tst_scriptPubKey, full_tx, 0, (SCRIPT_VERIFY_P2SH,))

	print("Txid of child of unvault TX:\t", str(b2lx(full_tx.GetTxid())))
	bitcoinrpc('sendrawtransaction {0}'.format(b2x(full_tx.serialize())))
