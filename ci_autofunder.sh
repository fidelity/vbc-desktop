#!/bin/bash
# Copyright 2021 FMR LLC <opensource@fidelity.com>
# SPDX-License-Identifer: MIT

RPC_BASE="bitcoin-cli -regtest -datadir=0 -rpcport=19010"
ACTIVE_ADDR="mx7YdYHgNhajUUDamBkPcLMFquDk1BW6v2"

RPC_NEW_ADDR=" getnewaddress"
RPC_MINE=" generatetoaddress "
RPC_101="101 "
RPC_1="1 "
RPC_IMPORT_ADDR=" importaddress "
RPC_FUND=" sendtoaddress "
FUND_1=" 1"
FUND_2=" 2"
FUND_3=" 3"
FUND_4=" 4"
FUND_5=" 5"
RPC_LIST=" listreceivedbyaddress 0 true true"


# Start CI, then init

# import deposit address
$RPC_BASE$RPC_IMPORT_ADDR$ACTIVE_ADDR

# Generate & import address
$RPC_BASE$RPC_NEW_ADDR > autofunder_addr.txt
NEW_ADDR=$(cat autofunder_addr.txt)
echo $NEW_ADDR

$RPC_BASE$RPC_IMPORT_ADDR$NEW_ADDR

# Generate UTXOs to use for deposit
# $RPC_BASE$RPC_MINE$RPC_101$NEW_ADDR > /dev/null

# Make multiple deposits
$RPC_BASE$RPC_FUND$ACTIVE_ADDR$FUND_1 > /dev/null
$RPC_BASE$RPC_FUND$ACTIVE_ADDR$FUND_2 > /dev/null
$RPC_BASE$RPC_FUND$ACTIVE_ADDR$FUND_3 > /dev/null
$RPC_BASE$RPC_FUND$ACTIVE_ADDR$FUND_4 > /dev/null
$RPC_BASE$RPC_FUND$ACTIVE_ADDR$FUND_5 > /dev/null
$RPC_BASE$RPC_MINE$RPC_1$NEW_ADDR > /dev/null

# display status to check TXIDs
$RPC_BASE$RPC_LIST

# On CI: vault, then unvault, then spend or clawback
