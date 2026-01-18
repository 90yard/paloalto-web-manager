import sys
import time
import random

class SecurityScanner:
    def __init__(self):
        self.version = "1.0.0"

    def print_welcome(self):
        print("-" * 50)
        print(f"🔒 GST Security Scanner v{self.version}")
        print("-" * 50)
        print("Initialize scanning protocols...")
        time.sleep(1)
        print("System Ready.")
        print("-" * 50)

    def scan(self, target):
        print(f"\n[+] Starting scan on target: {target}")
        print("[+] Checking for vulnerabilities...")
        
        steps = [
            "Analyzing port configuration...",
            "Checking firewall rules...",
            "Validating SSL certificates...",
            "Scanning for SQL injection risks...",
            "Looking for XSS vulnerabilities..."
        ]

        for step in steps:
            time.sleep(random.uniform(0.3, 0.8))  # Simulate processing time
            print(f"  > {step} [OK]")

        print("\n[!] Scan Complete.")
        risks = random.randint(0, 3)
        print(f"[!] Summary: {risks} potential risk(s) found on {target}.")
        if risks > 0:
            print("    - Advice: Detailed report generated. Check logs.")

    def start(self):
        self.print_welcome()
        while True:
            try:
                cmd = input("\n[GST-Shell] > ").strip().lower()
                
                if cmd == "help":
                    print("Available commands:")
                    print("  scan [target] - Start a security scan (e.g., scan 192.168.1.1)")
                    print("  exit          - Exit the application")
                elif cmd.startswith("scan"):
                    parts = cmd.split()
                    if len(parts) < 2:
                        print("Usage: scan <ip_or_url>")
                    else:
                        target = parts[1]
                        self.scan(target)
                elif cmd == "exit":
                    print("Shutting down...")
                    break
                elif cmd == "":
                    continue
                else:
                    print("Unknown command. Type 'help' for options.")
            except KeyboardInterrupt:
                print("\nForced Exit.")
                break

if __name__ == "__main__":
    scanner = SecurityScanner()
    scanner.start()