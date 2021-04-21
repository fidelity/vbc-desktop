# DISCLAIMER

This code is not production ready. DO NOT USE WITH MAINNET. DO NOT USE REAL FUNDS.

# vbc-desktop

The vaulted bitcoin custody project is made up of two repositories:

- vbc-desktop
- [vbc-board](https://github.com/fidelity/vbc-board)

This project enables self-custody of bitcoins through Vaults using pre-signed transaction and private-key deletion.

# Motivation

Private keys present a dangerous attack surface if they are easily accessible. They allow arbitrary signing of messages and thus, put funds at risk when not treated with proper care and security considerations. Even if they are not easily accessible, they are prone to accidental loss, bit rot, disaster or supply-chain attacks.

Vaults are a way to ensure funds are locked to a few different spending conditions with the use of deleted-keys and time-locks. From the [paper](https://arxiv.org/pdf/2005.11776.pdf)
"A bitcoin vault is a specific type of
covenant transaction that enforces a time-lock on the transfer of control of funds to a hot wallet, but enables an immediate
transfer of funds into a deep cold recovery wallet." 
If funds needs to be accessed, they are broadcast and will only be spendable after some arbitrary time-lock. At any point before the time-lock, the funds can be spent by the OP_ELSE branch of the script to a cold storage "Recovery Wallet". I.e. if there is suspicion of a theft attempt (unauthorized broadcast or suspicion of a compromised wallet to which that funds have been spent to), the funds can routed to a safe location.

<img width="687" alt="Screen Shot 2021-04-19 at 1 28 50 PM" src="https://user-images.githubusercontent.com/64624962/115278960-19d8f980-a114-11eb-9692-af0b41b19a5f.png">

<img width="805" alt="Screen Shot 2021-04-19 at 1 33 27 PM" src="https://user-images.githubusercontent.com/64624962/115278763-d7172180-a113-11eb-98c5-689c832bc245.png">



# Installation

## macOS

Set up Python 3.7

```bash
brew install python@3.8
echo 'export PATH="/usr/local/opt/python@3.8/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Set up virtual environment

```bash
python3.8 -m venv venv
source venv/bin/activate
```

Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
brew install openssl
```

### macOS 11 / Big Sur

Patch python-bitcoinlib

```bash
pushd venv/lib/python3.7/site-packages/bitcoin/core
```

edit key.py, line 35, to remove the 'or 'libeay32'' at the end.

```bash
popd
```

# How to Run

## Set up

Ensure that you have set up the board properly, per the instructions in [vbc-board](https://github.com/fidelity/vbc-board)

### Simulator

You will need to use the `simulator` branch of the vbc-board repo. To communicate the board simulator, the serial port needs to be changed. In messageHandler.py, comment out the line with the /dev/tty string and uncomment the three lines below `simulator connection`.

### Board

<img width="322" alt="Screen Shot 2021-04-19 at 1 11 38 PM" src="https://user-images.githubusercontent.com/64624962/115276443-04160500-a111-11eb-8bdd-f2e69bd478b9.png">

You will need the [STM32F469NI MCU](https://www.st.com/en/evaluation-tools/32f469idiscovery.html) and will also need to grasp a basic understanding of micropython.


You'll have the change the name of the device as it appears on your machine.
To do this, plug in both cables from the board to the computer run `ls -cltr /dev | grep tty`; remove the microUSB cable and run `ls -cltr /dev/ | grep tty` again.
Look at the output and find the missing name, it will be a rather long name on macOS.
In line 28 of messageHandler.py, change the /dev/ttyACM1 value to whatever your device name is -> /dev/[DEVICE-NAME].
  
## Run

Now run the code

`./interface.py`

## Instructions

You'll be presented with 8 cli options: init, fund, vault, unvault, spend, clawback, stop, help

Run init to get started

`init` : This will start Bitcoin regtest with 3 nodes running on localhost and mines past the CSV softfork.

`fund` : Creates a funding transaction used to fund the vaulted bitcoins

`vault` : Spends the funds into the vault (timelocked script).

`unvault` : Broadcasts the presigned transactions.

`mine_block` : Confirms the presigned transaction in mempool

To simulate regular external spend (non-theft attempt)

`simulate_timelock` : simulates timelock by mining the necessary amount of blocks

`spend` : will spend the presigned transaction through the OP_IF branch

To simulate emergency clawback spend (theft attempt)

`clawback` : will spend the presigned transaction through the OP_ELSE branch (not timelocked)

### Limitations

The `vault` and `unvault` commands can accept multiple TXIDs, but the board has a read buffer limited to 1024 bytes. In practice, this means TXs should only be vaulted or unvaulted individually or 2 at a time.

# Background

The genesis for this custody protocol can be traced back to this [2016 medium post]((https://medium.com/@BobMcElrath/re-imagining-cold-storage-with-timelocks-1f293bfe421f])) by Dr. Bob McElrath.

Significant guidance was given by Stepan Snigirev and the [cryptoadvance project](https://github.com/cryptoadvance).

# References

[Covenants Paper](https://arxiv.org/abs/2006.16714)

[Vaults Paper](https://arxiv.org/abs/2005.11776)

# See Also

<https://github.com/kanzure/python-vaults>

<https://github.com/JSwambo/bitcoin-vault>

https://github.com/revault/practical-revault
