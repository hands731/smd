import serial
import service
import sys
import requests
import time
import subprocess

def run_udevadm():
   for i in range(4):
       try:
           output = subprocess.check_output(["udevadm", "info", f"--name=/dev/ttyUSB"+str(i), "--attribute-walk"])
           output_str = output.decode("utf-8")
       
           if 'ftdi_sio' in output_str:
               print(" found 'ftdi_sio':\n")
               return str(i)
           else:
               print("does not contain 'ftdi_sio'")
       except subprocess.CalledProcessError as e:
           print(f"An error occurred for {device_name}: {e}")
   return 

def f_read(file_name):
   device = service.getHostName()
   raspiDir = "/home/JS/"+device+"/"
   data = ""
   with open(raspiDir+file_name, 'r', encoding="ISO-8859-1") as file:
       data = file.read()
   return data

def log_write(data):
   f=open("/home/pi/Serial/myylog.txt","a")
   f.write(data+"\n")
   f.close()

def calculate_transfer_time(file_size_kb, baudrate=9600, databits=7, stopbits=2, parity=1):
   file_size_bytes = file_size_kb * 1024  # KB to bytes
   total_bits = databits + stopbits + parity
   bytes_per_second = baudrate / (total_bits)
   return file_size_bytes / bytes_per_second




def sendFile(ftp_file):
    time.sleep(0.001)
    usb_num = run_udevadm()
    try:
        ser = serial.Serial(port='/dev/ttyUSB'+usb_num,
                        baudrate=9600,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.EIGHTBITS
                        )
        file_data = f_read(ftp_file)
        
        lines = file_data.split('\n')
        total_bytes_to_send = sum(len((line.strip() + '\r\n').encode('ISO-8859-1')) for line in lines)
        
        # 예상 전송 시간 계산 (KB 단위로 변환)
        estimated_time = calculate_transfer_time(total_bytes_to_send / 1024)
        show_progress = estimated_time > 10  # 10초 초과 여부 확인
        
        if show_progress:
            print(f"예상 전송 시간: {estimated_time:.1f}초")
            log_write(f"{date} - 예상 전송 시간: {estimated_time:.1f}초")
        
        total_bytes_sent = 0
        last_percentage = 0

        for line in lines:
            line = line.strip() + '\r\n'
            bytes_written = ser.write(line.encode('ISO-8859-1'))
            total_bytes_sent += bytes_written
            
            if show_progress:  # 10초 초과할 경우에만 진행률 표시
                current_percentage = (total_bytes_sent / total_bytes_to_send) * 100
                
                for threshold in [20, 40, 60, 80]:
                    if last_percentage < threshold and current_percentage >= threshold:
                        print(f"전송 진행률: {threshold}%")
                        log_write(f"{date} - 파일 전송 진행률: {threshold}%")
                
                last_percentage = current_percentage
            
            time.sleep(0.0001)

        if show_progress:
            print("전송 완료: 100%")
            log_write(f"{date} - 파일 전송 완료: 100%")
        ser.close()
       
    except KeyboardInterrupt:
        ser.close()
        sys.exit()
   
    except Exception as e:
        print(str(e))
        print("Exception!!!!!!")
        log_write(date+"////"+str(e))
        if str(e) == "[Errno 5] Input/output error" or "[Errno 2] No such file or directory: '/dev/ttyUSB0'" in str(e):           
            log_write(date+"/"+str(e))
            subprocess.call('sudo reboot now', shell=True)
        time.sleep(30)
          
date = service.getDateTime()
sendFile(sys.argv[1])
