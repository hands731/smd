import subprocess
from time import sleep

def check(process):
    string = 'ps -aux | grep /home/pi/'+process
    exec_string = "python3 /home/pi/"+process
    my=subprocess.check_output(string, shell=True).decode('utf-8')

    if exec_string not in my:
        subprocess.call(exec_string + " &", shell=True)

if __name__ == '__main__':
    for i in range(10):
        sleep(5)
        check("client.py")
        check("errorKill.py")
        
