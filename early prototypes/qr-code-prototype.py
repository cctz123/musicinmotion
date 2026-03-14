
# -- coding: utf-8 --
from Mv3dRgbdImport.Mv3dRgbdApi import *
from Mv3dRgbdImport.Mv3dRgbdDefine import *
import ctypes
import os

from music import audio_segment

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import threading
from Mv3dRgbdImport.Mv3dRgbdDefine import DeviceType_Ethernet, DeviceType_USB, MV3D_RGBD_FLOAT_EXPOSURETIME, \
    ParamType_Float, CoordinateType_Depth
import cv2
import threading
import numpy as np
from pyzbar.pyzbar import decode
import sounddevice as sd
import paho.mqtt.client as mqtt
import random
import ast



g_bExit = False

param_event_red = threading.Event()

server_addr = '192.168.0.81'
port = 1883

client_id = f'python-mqtt-{random.randint(0, 1000)}'
topic = "mqtt/topic"

username = "ESP32"
password = "MQTT"

var1, var2, var3, var4, var5, var6, var7, var8, var9, var10 = [0,0,0,0,0,0,0,0,0,0]


def mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
    client.username_pw_set(username, password)
    client.connect(server_addr, port)
    client.subscribe(topic)
    client.on_message = on_message
    client.loop_forever()

def on_message(client: mqtt.Client, userdata, msg):
    global var1, var2, var3, var4, var5, var6, var7, var8, var9, var10
    data_list = ast.literal_eval(msg.payload.decode('utf-8'))
    var1, var2, var3, var4, var5, var6, var7, var8,var9, var10 = data_list
    print(var1, var2, var3, var4, var5, var6,var7, var8, var9)



def generate_audio(frequency):
    duration = 2
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio_signal = (
            0.5 * np.sin(2 * np.pi * frequency * t) +
            0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
            0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
            0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
            0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
            0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
            0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
            0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def play_audio_red():
    global center_x
    global center_y
    global var1, var2, var3, var4, var5, var6, var7, var8, var9, var10
    scales = {
        "do": 261.63,
        "re": 293.66,
        "mi": 329.63,
        "fa": 349.23,
        "sol": 392.00,
        "la": 440.00,
        "ti": 493.88
    }
    while True:
        param_event_red.wait()
        if 0 <= center_x <= 320 and 0 <= center_y <= 360 and var6 < -30 and var10 >= 9999.9:
            frequency = scales["do"]
            audio_signal = generate_audio(frequency)
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        elif 320 <= center_x <= 640 and 0 <= center_y <= 360:
            frequency = scales["re"]
            audio_signal = generate_audio(frequency)
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        elif 640 <= center_x <= 960 and 0 <= center_y <= 360:
            frequency = scales["mi"]
            audio_signal = generate_audio(frequency)
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        elif 960 <= center_x <= 1280 and 0 <= center_y <= 360:
            frequency = scales["fa"]
            audio_signal = generate_audio(frequency)
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        elif 0 <= center_x <= 320 and 360 <= center_y <= 720:
            frequency = scales["sol"]
            audio_signal = generate_audio(frequency)
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        elif 320 <= center_x <= 640 and 360 <= center_y <= 720:
            frequency = scales["la"]
            audio_signal = generate_audio(frequency)
            sd.wait()
            sd.play(audio_signal, samplerate=44100)
        elif 640 <= center_x <= 960 and 360 <= center_y <= 720:
            frequency = scales["ti"]
            audio_signal = generate_audio(frequency)
            audio_signal = audio_signal - 1
            sd.play(audio_signal, samplerate=44100)
            sd.wait()
        else:
            pass
        param_event_red.clear()



def draw_rectangle():
    start_point1 = (0, 0)
    end_point1 = (320, 360)
    start_point2 = (320, 0)
    end_point2 = (640, 360)
    start_point3 = (640, 0)
    end_point3 = (960, 360)
    start_point4 = (960, 0)
    end_point4 = (1280, 360)
    start_point5 = (0, 360)
    end_point5 = (320, 720)
    start_point6 = (320, 360)
    end_point6 = (640, 720)
    start_point7 = (960, 360)
    end_point7 = (960, 720)
    start_point8 = (960, 360)
    end_point8 = (1280, 720)

    rectangle_color = (0, 250, 0)
    thickness = 2

    cv2.rectangle(bgf, start_point1, end_point1, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point2, end_point2, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point3, end_point3, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point4, end_point4, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point5, end_point5, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point6, end_point6, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point7, end_point7, rectangle_color, thickness)
    cv2.rectangle(bgf, start_point8, end_point8, rectangle_color, thickness)

    cv2.putText(bgf, "DO", (160, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "RE", (480, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "MI", (800, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "FA", (1120, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "SO", (160, 540), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "LA", (480, 540), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))
    cv2.putText(bgf, "TI", (800, 540), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 225, 0))


if __name__ == "__main__":

    center_x = -1
    center_y = -1

    task_thread_red = threading.Thread(target = play_audio_red)
    task_thread_red.start()
    task_thread_mqtt = threading.Thread(target=play_audio_red)
    task_thread_mqtt.start()



    sleep_once = True
    nDeviceNum = ctypes.c_uint(0)
    nDeviceNum_p = byref(nDeviceNum)
    ret = Mv3dRgbd.MV3D_RGBD_GetDeviceNumber(DeviceType_Ethernet | DeviceType_USB, nDeviceNum_p)  # 获取设备数量
    if ret != 0:
        print("MV3D_RGBD_GetDeviceNumber fail! ret[0x%x]" % ret)
        os.system('pause')
        sys.exit()
    if nDeviceNum == 0:
        print("find no device!")
        os.system('pause')
        sys.exit()
    print("Find devices numbers:", nDeviceNum.value)

    stDeviceList = MV3D_RGBD_DEVICE_INFO_LIST()
    net = Mv3dRgbd.MV3D_RGBD_GetDeviceList(DeviceType_Ethernet | DeviceType_USB, pointer(stDeviceList.DeviceInfo[0]),
                                           20, nDeviceNum_p)
    for i in range(0, nDeviceNum.value):
        print("\ndevice: [%d]" % i)
        strModeName = ""
        for per in stDeviceList.DeviceInfo[i].chModelName:
            strModeName = strModeName + chr(per)
        print("device model name: %s" % strModeName)

        strSerialNumber = ""
        for per in stDeviceList.DeviceInfo[i].chSerialNumber:
            strSerialNumber = strSerialNumber + chr(per)
        print("device SerialNumber: %s" % strSerialNumber)
    # 创建相机示例
    camera = Mv3dRgbd()
    nConnectionNum = 0
    # 打开设备
    ret = camera.MV3D_RGBD_OpenDevice(pointer(stDeviceList.DeviceInfo[int(nConnectionNum)]))
    if ret != 0:
        print("MV3D_RGBD_OpenDevice fail! ret[0x%x]" % ret)
        os.system('pause')
        sys.exit()

    # 开始取流
    ret = camera.MV3D_RGBD_Start()
    if ret != 0:
        print("start fail! ret[0x%x]" % ret)
        camera.MV3D_RGBD_CloseDevice()
        os.system('pause')
        sys.exit()



    while True:
        # 获取图像线程
        stFrameData = MV3D_RGBD_FRAME_DATA()
        ret = camera.MV3D_RGBD_FetchFrame(pointer(stFrameData), 1000)
        if ret == 0:
            p_color = ctypes.string_at(stFrameData.stImageData[1].pData, stFrameData.stImageData[1].nDataLen)
            p_depth = ctypes.string_at(stFrameData.stImageData[0].pData, stFrameData.stImageData[0].nDataLen)

            color_img = np.frombuffer(p_color, dtype=np.uint8)
            color_img = color_img.reshape((stFrameData.stImageData[1].nHeight, stFrameData.stImageData[1].nWidth, 2))

            depth_img = np.frombuffer(p_depth, dtype=np.uint16)
            depth_img = depth_img.reshape((stFrameData.stImageData[0].nHeight, stFrameData.stImageData[0].nWidth))

            bgf = cv2.cvtColor(color_img, cv2.COLOR_YUV2RGB_YUYV)
            bgf = cv2.cvtColor(bgf, cv2.COLOR_RGB2BGR)
            decode_objects = decode(bgf)
            for obj in decode_objects:
                qr_data = obj.data.decode('utf-8')
                print(qr_data)

                (x, y, w, h) = obj.rect  # left bottom corner
                cv2.rectangle(bgf, (x, y), (x + w, y + h), (255, 0, 0), 2)

                center_x = x + w // 2
                center_y = y + h // 2
                print(f"QR_Code center: ({center_x}, {center_y})")


                cv2.putText(bgf, qr_data, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                param_event_red.set()

            draw_rectangle()
            cv2.imshow("Box select", bgf)
            mykey = cv2.waitKey(1)
            # 按q退出循环，0xFF是为了排除一些功能键对q的ASCII码的影响
            if mykey & 0xFF == ord('q'):
                break

            # play_audio_red()

        else:
            print("no data[0x%x]" % ret)
        if g_bExit == True:
            break

    # 停止取流
    ret = camera.MV3D_RGBD_Stop()
    if ret != 0:
        print("stop fail! ret[0x%x]" % ret)
        os.system('pause')
        sys.exit()

    # 销毁句柄
    ret = camera.MV3D_RGBD_CloseDevice()
    if ret != 0:
        print("CloseDevice fail! ret[0x%x]" % ret)
        os.system('pause')
        sys.exit()

    sys.exit()
