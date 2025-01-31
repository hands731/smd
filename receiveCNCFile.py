import serial  
import time
import os
import signal
import sys
import subprocess
import service
import requests

# 시리얼 포트 객체를 전역 변수로 선언
ser = None

def run_udevadm():
  for i in range(4):
      try:
          output = subprocess.check_output(["udevadm", "info", f"--name=/dev/ttyUSB"+str(i), "--attribute-walk"])
          output_str = output.decode("utf-8")
      
          if 'ftdi_sio' in output_str:
              print(" found 'ftdi_sio':\n")
              return str(i)
          else:
              print("does not contain 'FTDI-uart'")
      except subprocess.CalledProcessError as e:
          print(f"An error occurred for {device_name}: {e}")
  return 

def notify_file_completion(device, filename):
   try:
       url = "http://218.156.98.198/tomes/fileReadFinish"
       data = {
           "equip_id": device,
           "file_name": filename
       }
       response = requests.post(url, json=data)
       response_data = response.json()
       if response_data.get("device") == "ok":
           print("파일 읽기 완료 알림 성공")
       return True
   except Exception as e:
       print(f"완료 API 호출 실패: {str(e)}")
       return False

def notify_file_start(device, filename):
   try:
       url = "http://218.156.98.198/tomes/fileReadStart"
       data = {
           "equip_id": device,
           "file_name": filename
       }
       response = requests.post(url, json=data)
       response_data = response.json()
       if response_data.get("device") == "ok":
           print("파일 읽기 시작 알림 성공")
       return True
   except Exception as e:
       print(f"시작 API 호출 실패: {str(e)}")
       return False

def read_with_retry(ser, max_retries=3):
   for _ in range(max_retries):
       try:
           res = ser.readline()
           if res:
               return res
           time.sleep(0.1)  # 데이터가 없을 경우 잠시 대기
       except Exception as e:
           print(f"읽기 재시도 중: {str(e)}")
           time.sleep(0.1)
   return None
def get_unique_filename(base_path, filename):
    """
    파일명이 중복될 경우 _1, _2 등을 추가하여 고유한 파일명 생성
    """
    name, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    full_path = os.path.join(base_path, new_filename)
    
    while os.path.exists(full_path):
        new_filename = f"{name}_{counter}{ext}"
        full_path = os.path.join(base_path, new_filename)
        counter += 1
    
    return new_filename
# 저장할 디렉토리 경로
device = service.getHostName()
SAVE_DIR = '/home/JS/'+device

try:
   usb_num = run_udevadm()

   ser = serial.Serial(port='/dev/ttyUSB'+usb_num,
           baudrate=9600,
           parity=serial.PARITY_NONE,
           stopbits=serial.STOPBITS_ONE,
           bytesize=serial.EIGHTBITS,
           timeout = 3)

   # 시리얼 버퍼 비우기
   ser.reset_input_buffer()
   ser.reset_output_buffer()
   time.sleep(0.1)
   print("시리얼 포트 준비 완료. 데이터를 기다리는 중...")

   # 첫 줄을 읽어서 파일명으로 사용
   while True:
       try:
           if not ser.is_open:
               break
           first_line = read_with_retry(ser)
           if first_line:
               print("받은 데이터:", first_line)
               
               # null 바이트 제거 후 디코딩
               filename = first_line.replace(b'\x00', b'').decode('ISO-8859-1').strip()
               if filename:
                   # 백슬래시로 나누고 가장 마지막 부분을 파일명으로 사용
                   safe_filename = filename.split('\\')[-1].strip("'")
                       # 중복 검사 및 고유 파일명 생성
                   safe_filename = get_unique_filename(SAVE_DIR, safe_filename)
                   # 파일 저장 경로 설정
                   filename = os.path.join(SAVE_DIR, safe_filename)
                   print("생성할 파일명:", safe_filename)
                   
                   # sudo로 빈 파일 생성하고 권한 설정
                   subprocess.run(['sudo', 'touch', filename])
                   subprocess.run(['sudo', 'chown', 'JS:JS', filename])
                   subprocess.run(['sudo', 'chmod', '664', filename])  # rw-rw-r-- 권한 설정
                   
                   notify_file_start(device, safe_filename)
                   break
       except Exception as e:
           print(f"첫 줄 읽기 오류: {str(e)}")
           time.sleep(0.1)  # 에러 발생 시 잠시 대기
           continue

   if ser.is_open:  # 정상적으로 파일명을 받았을 때만 실행
       process = None
       try:
           command = f'sudo tee {filename}'
           process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE)
           
           line_count = 0
           received_data = False
           buffer = b''  # 이전 데이터를 저장할 버퍼

           while True:
               try:
                   res = read_with_retry(ser)
                   if res:
                       received_data = True
                       # 이전 버퍼에 있는 데이터와 합치기
                       if buffer:
                           res = buffer + res
                           buffer = b''
                       
                       decoded_data = res.replace(b'\x00', b'').decode('ISO-8859-1').strip()
                       if decoded_data:
                           line_count += 1
                           if line_count > 1:
                               print(decoded_data)
                               process.stdin.write(f'{decoded_data}\n'.encode())
                               process.stdin.flush()
                               if 'M30' in decoded_data:
                                   print("파일 수신 완료 (M30 감지)")
                                   process.stdin.close()
                                   process.wait()
                                   notify_file_completion(device, safe_filename)
                                   ser.close()
                                   sys.exit(0)
                   elif received_data:
                       # 읽기 실패 시 현재 버퍼 확인
                       if ser.in_waiting:  # 수신 버퍼에 데이터가 있는 경우
                           buffer += ser.read(ser.in_waiting)
                       else:
                           print("데이터 수신 완료 (추가 데이터 없음)")
                           if process:
                               process.stdin.close()
                               process.wait()
                           notify_file_completion(device, safe_filename)
                           ser.close()
                           sys.exit(0)
                       time.sleep(0.1)
                               
               except Exception as e:
                   print(f"읽기 오류: {str(e)}")
                   # 오류 발생 시 현재 버퍼 내용 저장
                   if ser.in_waiting:
                       buffer += ser.read(ser.in_waiting)
                   time.sleep(0.1)
                   continue

       except Exception as e:
           print(f"프로그램 오류: {str(e)}")
           if process:
               process.stdin.close()
               process.wait()

except Exception as e:
   print(f"프로그램 오류: {str(e)}")

finally:
   # 프로그램 종료 시 시리얼 포트 정리
   if ser is not None and ser.is_open:
       try:
           ser.reset_input_buffer()
           ser.reset_output_buffer()
           ser.close()
           print('시리얼 포트가 안전하게 종료되었습니다.')
       except Exception as e:
           print(f"포트 종료 중 오류 발생: {str(e)}")
