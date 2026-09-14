import subprocess
import time
import os

while True:
    os.system("color a")
    os.system("title crumb Server")
    print("Starting crumb...")
    
    subprocess.run(["python", "bot.py"])
    
    print("Bot stopped. Restarting in 5 seconds...")
    time.sleep(5)