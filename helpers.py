# Copyright 2021 FMR LLC <opensource@fidelity.com>
# SPDX-License-Identifer: MIT

"""utilies for CI setup, RPC calls, and reading to disk"""

import os
import time
import json
from hashlib import sha256
from bitcoin import SelectParams
from bitcoin.core import *
from bitcoin.core.key import *
from bitcoin.core.script import *
from bitcoin.core.scripteval import *
from bitcoin.bech32 import CBech32Data
from bitcoin.wallet import *
SelectParams('regtest')

mining_addr = 0
node_count = 3
bitcoind_flags = '-regtest -txindex -server -daemon -minrelaytxfee=0.0 -fallbackfee=0.00001'

def bitcoinrpc(args, i=0):
    """
    interface to bitcoin-cli RPC calls
    """
    data = os.popen('bitcoin-cli -regtest -datadir='+str(i)+' -rpcport=1901'+str(i)+' '+args).read()
    if data and (data[0] == '{' or data[0] == '['):
        return json.loads(data)
    return data.rstrip()
def stop_nodes(num_nodes=node_count):
    for i in range(num_nodes):
        os.system('pkill -F '+str(i)+'/regtest/bitcoind.pid >/dev/null 2>&1')
    time.sleep(1)
def reset_txs():
    os.system('rm -f transactions.csv')
    os.system('rm -f unvaulted.csv')
    os.system('touch transactions.csv')
    os.system('touch unvaulted.csv')
def reset_regtest(num_nodes=node_count):
    """
    stop regtest nodes, reset their data directories
    remove any record of vaulted or unvaulted transactions
    """
    stop_nodes(num_nodes)
    for i in range(num_nodes):
        os.system('rm -rf '+str(i))
    reset_txs()
    for i in range(num_nodes):
        os.mkdir(str(i))
    os.system('touch transactions.csv')
    os.system('touch unvaulted.csv')
def ignition(mine_past_forks=True):
    """
    spins up a local regtest server consisting of 3 nodes running on localhost
    mines past soft forks by default
    """
    global mining_addr
    stop_nodes(node_count)
    for i in range(node_count):
        os.system('bitcoind '+bitcoind_flags+' -datadir='+str(i)+' -port=1900'+str(i)+' -rpcport=1901'+str(i))
    time.sleep(3)
    for i in range(node_count):
        bitcoinrpc('addnode localhost:1900'+str((i+1)%node_count)+' add', i)
        bitcoinrpc('addnode localhost:1900'+str((i+2)%node_count)+' add', i)
    time.sleep(1)

    # make sure our default wallet exists
    if os.path.isfile('0/regtest/wallets/CI/wallet.dat'):
        bitcoinrpc('loadwallet CI')
    else:
        bitcoinrpc('createwallet CI')
    mining_addr = bitcoinrpc('getnewaddress')
    if mine_past_forks and int(bitcoinrpc('getblockchaininfo')["blocks"]) < 1401:
        #generating 1400 blocks to roll past soft-forks
        generate(1400)
def jprint(j):
    """
    json pretty printing
    """
    print(json.dumps(j, indent=4, separators=(',',': ')))
def generate(blocks):
    """
    generates n blocks
    """
    return bitcoinrpc('generatetoaddress ' + str(blocks) + ' ' + str(mining_addr))
def getconfirmations(txid):
    """
    get TX confirmations
    """
    return bitcoinrpc('getrawtransaction ' + str(txid) + ' true')["confirmations"]
def makekey(s):
    """
    enerates a bitcoin private key from a secret s
    """
    return CBitcoinSecret.from_secret_bytes(sha256(s).digest())
def tobechaddress(s):
    """
    convert bytes to bech32 address
    """
    return CBech32BitcoinAddress.from_bytes(0, CBech32Data(s))
def encodelocktime(locktime):
    """
    generate the locktime opcodes for any valid locktime
    returns a list of opcodes
    """
    print('encoding locktime', locktime)
    opcode_list = [OP_IF]
    if locktime >= 65536 or locktime < 1:
        raise ValueError("Invalid relative locktime! Must be on [1, 65536)")
    # small values are directly encoded
    if locktime <= 16:
        opcode_list.append(CScriptOp.encode_op_n(locktime))
    # 1-byte locktime
    elif locktime < 256:
        timelock_hex = f'{locktime:0>2X}'
        # check for sign bit on our timelock value
        if locktime // 2**7 == 1:
            # 'push' opcode
            opcode_list.append(CScriptOp(0x02))
            opcode_list.append(CScriptOp(int(timelock_hex, 16)))
            # sign byte
            opcode_list.append(CScriptOp(0x00))
        else:
            opcode_list.append(CScriptOp(0x01))
            opcode_list.append(CScriptOp(int(timelock_hex, 16)))
    # 2-byte locktime
    else:
        timelock_hex = f'{locktime:0>4X}'
        if locktime // 2**15 == 1:
            opcode_list.append(CScriptOp(0x03))
            # push each timelock byte, LSB first
            opcode_list.append(CScriptOp(int(timelock_hex[2:], 16)))
            opcode_list.append(CScriptOp(int(timelock_hex[:2], 16)))
            opcode_list.append(CScriptOp(0x00))
        else:
            opcode_list.append(CScriptOp(0x02))
            opcode_list.append(CScriptOp(int(timelock_hex[2:], 16)))
            opcode_list.append(CScriptOp(int(timelock_hex[:2], 16)))

    return opcode_list
def getDiskLocktime(txid):
    """
    fetch the locktime for an unvaulted TX
    to create a child TX; return locktime
    """
    locktime = [pair[1] for pair in getDiskTxids("unvaulted") if pair[0] == txid]
    return int(locktime[0])
def getDiskTxids(file):
    """
    fetch vaulted or unvaulted TXs from disk
    return type is list((txid, timelock))
    """
    if file == 'vaulted':
        with open("transactions.csv", 'r') as fi:
            return CsvReader(fi, 'vaulted')
    elif file == 'unvaulted':
        with open("unvaulted.csv", 'r') as fi:
            return CsvReader(fi, 'unvaulted')
    return []
def CsvReader(file_handle, file_type):
    """
    parse CSVs from disk
    return type is list((txid, timelock))
    """
    txid_list = list()

    for row in file_handle:
        row = row.strip().split(',')
        if file_type == 'vaulted':
            txid_list.append((row[0], row[3]))
        elif file_type == 'unvaulted':
            txid_list.append((row[0], row[1]))

    return txid_list
