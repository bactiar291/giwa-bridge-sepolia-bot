import os
import time
from web3 import Web3, exceptions
from dotenv import load_dotenv

load_dotenv()

SEPOLIA_RPC = "https://ethereum-sepolia-rpc.publicnode.com"
GIWA_RPC = "https://sepolia-rpc.giwa.io"
BRIDGE_CONTRACT_ADDRESS = "0x956962C34687A954e611A83619ABaA37Ce6bC78A"

BRIDGE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_to", "type": "address"},
            {"internalType": "uint256", "name": "_value", "type": "uint256"},
            {"internalType": "uint64", "name": "_gasLimit", "type": "uint64"},
            {"internalType": "bool", "name": "_isCreation", "type": "bool"},
            {"internalType": "bytes", "name": "_data", "type": "bytes"}
        ],
        "name": "depositTransaction",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]

def get_eth_balance(w3, address):
    bal_wei = w3.eth.get_balance(address)
    return float(w3.from_wei(bal_wei, 'ether'))

def _get_private_key_from_env_or_prompt():
    pk = os.getenv("PRIVATE_KEY")
    if pk:
        if not pk.startswith("0x"):
            pk = "0x" + pk
        return pk
    print("PRIVATE_KEY tidak ditemukan di .env")
    use_input = input("Mau masukkan private key sekarang? (y/n): ")
    if use_input.lower() != "y":
        raise SystemExit("Private key tidak disediakan. Tambahkan PRIVATE_KEY di .env lalu jalankan lagi.")
    private_key = input("Masukkan private key: ").strip()
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    return private_key

def bridge_eth():
    watermark = "bactiar291 | auto bridge sepolia -> giwa"
    print("\n" + "="*len(watermark))
    print(watermark)
    print("="*len(watermark) + "\n")

    sepolia_w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC))
    giwa_w3 = Web3(Web3.HTTPProvider(GIWA_RPC))

    if not sepolia_w3.is_connected():
        print("Gagal koneksi ke Sepolia RPC")
        return
    if not giwa_w3.is_connected():
        print("Gagal koneksi ke Giwa RPC")
        return

    try:
        private_key = _get_private_key_from_env_or_prompt()
    except SystemExit as e:
        print(str(e))
        return
    except Exception as e:
        print("Error mendapatkan private key:", e)
        return

    try:
        account = sepolia_w3.eth.account.from_key(private_key)
    except Exception:
        print("Private key tidak valid")
        return
    address = account.address

    sep_balance = get_eth_balance(sepolia_w3, address)
    giwa_balance = get_eth_balance(giwa_w3, address)
    print(f"ADDRESS: {address}")
    print(f"Saldo awal Sepolia: {sep_balance:.18f} ETH")
    print(f"Saldo awal Giwa   : {giwa_balance:.18f} ETH\n")

    try:
        amount = float(input("Masukkan jumlah ETH yang ingin di-bridge per tx (contoh: 0.01): "))
        repeat_count = int(input("Berapa kali menjalankan bridge? sabaraha??: "))
    except ValueError:
        print("Input tidak valid")
        return

    amount_wei = sepolia_w3.to_wei(amount, 'ether')

    try:
        gas_price = int(sepolia_w3.eth.gas_price)
        gas_price = int(gas_price * 1.10)
    except Exception:
        gas_price = sepolia_w3.to_wei(20, 'gwei')

    bridge_contract = sepolia_w3.eth.contract(
        address=Web3.to_checksum_address(BRIDGE_CONTRACT_ADDRESS),
        abi=BRIDGE_ABI
    )

    try:
        sample_estimate = bridge_contract.functions.depositTransaction(
            Web3.to_checksum_address(address),
            amount_wei,
            21000,
            False,
            b''
        ).estimate_gas({'from': address, 'value': amount_wei})
        gas_limit_for_calc = int(sample_estimate * 1.2)
    except Exception:
        gas_limit_for_calc = 90000

    gas_cost_total_wei = gas_price * gas_limit_for_calc * repeat_count
    gas_cost_total_eth = float(sepolia_w3.from_wei(gas_cost_total_wei, 'ether'))
    total_needed_eth = (amount * repeat_count) + gas_cost_total_eth

    print(f"Estimasi gasPrice (legacy): {sepolia_w3.from_wei(gas_price, 'gwei'):.3f} gwei")
    print(f"Estimasi gas per tx (gas limit): {gas_limit_for_calc}")
    print(f"Estimasi total biaya gas untuk {repeat_count} tx: {gas_cost_total_eth:.12f} ETH")
    print(f"Total ETH diperlukan (amount * count + gas): {total_needed_eth:.12f} ETH\n")

    current_balance_wei = sepolia_w3.eth.get_balance(address)
    if sepolia_w3.to_wei(total_needed_eth, 'ether') > current_balance_wei:
        print("Saldo Sepolia tidak cukup untuk jumlah dan biaya yang diperkirakan.")
        return

    confirm = input("Lanjutkan pengiriman? (y/n): ")
    if confirm.lower() != 'y':
        print("Dibatalkan.")
        return

    successful_txs = 0

    for i in range(repeat_count):
        print(f"\n=== Mengirim transaksi {i+1}/{repeat_count} ===")
        try:
            nonce = sepolia_w3.eth.get_transaction_count(address)
            try:
                estimated_gas = bridge_contract.functions.depositTransaction(
                    Web3.to_checksum_address(address),
                    amount_wei,
                    21000,
                    False,
                    b''
                ).estimate_gas({'from': address, 'value': amount_wei})
                gas_limit = int(estimated_gas * 1.2)
                print(f"Estimate gas: {estimated_gas}, menggunakan gas limit: {gas_limit}")
            except Exception:
                gas_limit = gas_limit_for_calc
                print(f"Gagal estimate gas, gunakan fallback gas limit: {gas_limit}")

            tx = bridge_contract.functions.depositTransaction(
                Web3.to_checksum_address(address),
                amount_wei,
                21000,
                False,
                b''
            ).build_transaction({
                'from': address,
                'value': amount_wei,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': 11155111
            })

            signed_tx = sepolia_w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = sepolia_w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = Web3.to_hex(tx_hash)
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = "0x" + tx_hash_hex
            etherscan_url = f"https://sepolia.etherscan.io/tx/{tx_hash_hex}"
            print(f"Tx dikirim: {tx_hash_hex} (gasPrice {sepolia_w3.from_wei(gas_price,'gwei'):.3f} gwei)")

            try:
                receipt = sepolia_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                if receipt.status == 1:
                    print("Status: SUCCESS")
                    print(f"Lihat di Etherscan: {etherscan_url}")
                    successful_txs += 1
                else:
                    print("Status: FAILED (status 0). Lihat receipt untuk detail.")
                    print(receipt)
                    print(f"Lihat di Etherscan: {etherscan_url}")
            except exceptions.TimeExhausted:
                print("Tunggu konfirmasi timeout. Transaksi mungkin masih pending.")
                print(f"Pantau di Etherscan: {etherscan_url}")

            sep_balance = get_eth_balance(sepolia_w3, address)
            giwa_balance = get_eth_balance(giwa_w3, address)
            print(f"Saldo saat ini Sepolia: {sep_balance:.18f} ETH")
            print(f"Saldo saat ini Giwa   : {giwa_balance:.18f} ETH")
            if i < repeat_count - 1:
                print("Menunggu 15 detik sebelum transaksi berikutnya...")
                time.sleep(15)

        except Exception as e:
            print(f"Error pada transaksi {i+1}: {e}")
            if "nonce" in str(e).lower():
                print("Terjadi masalah nonce — refresh koneksi dan lanjutkan.")
                sepolia_w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC))

    final_sep = get_eth_balance(sepolia_w3, address)
    final_giwa = get_eth_balance(giwa_w3, address)

    print("\n=== Proses selesai ===")
    print(f"Transaksi berhasil: {successful_txs}/{repeat_count}")
    print(f"Saldo akhir Sepolia: {final_sep:.18f} ETH")
    print(f"Saldo akhir Giwa   : {final_giwa:.18f} ETH\n")
    print("="*len(watermark))
    print(watermark)
    print("="*len(watermark) + "\n")

if __name__ == "__main__":
    bridge_eth()
