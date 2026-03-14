
# 这一版实现了根据用户的动作去反应到底检查到了何种动作
import cv2
import mediapipe as mp
import math
import sys
import argparse
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QPushButton, QMessageBox, QMainWindow)
from PyQt5.QtGui import QImage, QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QTimer

# 语言设置（通过命令行参数 --lang 控制，默认 "CN"，仅支持 "CN" 或 "EN"）
language = "CN"


# 初始化MediaPipe工具
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# 定义需要隐藏的头部和手部关键点索引
HIDDEN_LANDMARKS = [
    mp_pose.PoseLandmark.NOSE,  # 鼻子
    mp_pose.PoseLandmark.LEFT_EYE_INNER,  # 左眼内
    mp_pose.PoseLandmark.LEFT_EYE,  # 左眼
    mp_pose.PoseLandmark.LEFT_EYE_OUTER,  # 左眼外
    mp_pose.PoseLandmark.RIGHT_EYE_INNER,  # 右眼内
    mp_pose.PoseLandmark.RIGHT_EYE,  # 右眼
    mp_pose.PoseLandmark.RIGHT_EYE_OUTER,  # 右眼外
    mp_pose.PoseLandmark.LEFT_EAR,  # 左耳
    mp_pose.PoseLandmark.RIGHT_EAR,  # 右耳
    mp_pose.PoseLandmark.MOUTH_LEFT,  # 左嘴角
    mp_pose.PoseLandmark.MOUTH_RIGHT,  # 右嘴角
    mp_pose.PoseLandmark.LEFT_WRIST,  # 左手腕
    mp_pose.PoseLandmark.RIGHT_WRIST,  # 右手腕
    mp_pose.PoseLandmark.LEFT_PINKY,  # 左小指
    mp_pose.PoseLandmark.RIGHT_PINKY,  # 右小指
    mp_pose.PoseLandmark.LEFT_INDEX,  # 左食指
    mp_pose.PoseLandmark.RIGHT_INDEX,  # 右食指
    mp_pose.PoseLandmark.LEFT_THUMB,  # 左拇指
    mp_pose.PoseLandmark.RIGHT_THUMB  # 右拇指
]

# 自定义连接线（只保留身体主干）
CUSTOM_CONNECTIONS = [
    # 左半身
    (mp_pose.PoseLandmark.LEFT_SHOULDER, mp_pose.PoseLandmark.LEFT_ELBOW),
    (mp_pose.PoseLandmark.LEFT_ELBOW, mp_pose.PoseLandmark.LEFT_WRIST),
    (mp_pose.PoseLandmark.LEFT_SHOULDER, mp_pose.PoseLandmark.LEFT_HIP),
    (mp_pose.PoseLandmark.LEFT_HIP, mp_pose.PoseLandmark.LEFT_KNEE),
    (mp_pose.PoseLandmark.LEFT_KNEE, mp_pose.PoseLandmark.LEFT_ANKLE),
    (mp_pose.PoseLandmark.LEFT_HEEL, mp_pose.PoseLandmark.LEFT_ANKLE),
    (mp_pose.PoseLandmark.LEFT_FOOT_INDEX, mp_pose.PoseLandmark.LEFT_ANKLE),
    (mp_pose.PoseLandmark.LEFT_FOOT_INDEX, mp_pose.PoseLandmark.LEFT_HEEL),

    # 右半身
    (mp_pose.PoseLandmark.RIGHT_SHOULDER, mp_pose.PoseLandmark.RIGHT_ELBOW),
    (mp_pose.PoseLandmark.RIGHT_ELBOW, mp_pose.PoseLandmark.RIGHT_WRIST),
    (mp_pose.PoseLandmark.RIGHT_SHOULDER, mp_pose.PoseLandmark.RIGHT_HIP),
    (mp_pose.PoseLandmark.RIGHT_HIP, mp_pose.PoseLandmark.RIGHT_KNEE),
    (mp_pose.PoseLandmark.RIGHT_KNEE, mp_pose.PoseLandmark.RIGHT_ANKLE),
    (mp_pose.PoseLandmark.RIGHT_HEEL, mp_pose.PoseLandmark.RIGHT_ANKLE),
    (mp_pose.PoseLandmark.RIGHT_FOOT_INDEX, mp_pose.PoseLandmark.RIGHT_ANKLE),
    (mp_pose.PoseLandmark.RIGHT_FOOT_INDEX, mp_pose.PoseLandmark.RIGHT_HEEL),

    # 躯干连接
    (mp_pose.PoseLandmark.LEFT_SHOULDER, mp_pose.PoseLandmark.RIGHT_SHOULDER),
    (mp_pose.PoseLandmark.LEFT_HIP, mp_pose.PoseLandmark.RIGHT_HIP)
]


# 计算三个点之间的角度
def calculate_angle(a, b, c):
    # 计算向量BA和BC
    ba = [a.x - b.x, a.y - b.y]
    bc = [c.x - b.x, c.y - b.y]

    # 计算点积
    dot_product = ba[0] * bc[0] + ba[1] * bc[1]

    # 计算模长
    mod_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
    mod_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)

    # 计算余弦值
    cos_angle = dot_product / (mod_ba * mod_bc)

    # 防止浮点误差导致的值超出[-1,1]范围
    cos_angle = max(-1.0, min(1.0, cos_angle))

    # 计算角度（弧度转角度）
    angle = math.degrees(math.acos(cos_angle))
    return angle


# 检测树式姿势
def check_tree_pose(landmarks):
    # 获取关键点
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]

    # 判断哪只脚是支撑脚（位置较低的那只脚）
    if left_ankle.y > right_ankle.y:  # 注意：y值越大，在图像中位置越低
        standing_leg = "LEFT"
        lifted_ankle = right_ankle
        standing_knee = left_knee
        standing_hip = left_hip
    else:
        standing_leg = "RIGHT"
        lifted_ankle = left_ankle
        standing_knee = right_knee
        standing_hip = right_hip

    # 1. 检查抬起的脚是否靠近支撑腿的大腿内侧
    # 计算抬起的脚踝与支撑腿膝盖的水平距离
    horizontal_distance = abs(lifted_ankle.x - standing_knee.x)

    # 2. 检查抬起的脚是否在支撑腿膝盖高度附近
    # 理想情况下，抬起的脚踝应该在支撑腿膝盖和臀部之间
    vertical_position_ok = standing_hip.y < lifted_ankle.y < standing_knee.y

    # 3. 检查支撑腿是否伸直
    if standing_leg == "LEFT":
        knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    else:
        knee_angle = calculate_angle(right_hip, right_knee, right_ankle)

    # 4. 检查身体是否保持直立
    # 计算肩膀中心点
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    shoulder_center = [(left_shoulder.x + right_shoulder.x) / 2,
                       (left_shoulder.y + right_shoulder.y) / 2]

    # 计算髋部中心点
    hip_center = [(left_hip.x + right_hip.x) / 2,
                  (left_hip.y + right_hip.y) / 2]

    # 计算肩膀中心到髋部中心的垂直线
    vertical_alignment = abs(shoulder_center[0] - hip_center[0])

    # 判断标准：水平距离小，垂直位置合适，膝盖角度接近180度，身体垂直对齐
    is_standard = (horizontal_distance < 0.1 and
                   vertical_position_ok and
                   knee_angle > 170 and
                   vertical_alignment < 0.05)

    return is_standard


# 检测下犬式姿势
def check_downward_dog(landmarks):
    # 获取关键点
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_elbow = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
    right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]

    # 计算身体各部位中心点
    wrist_center = [(left_wrist.x + right_wrist.x) / 2,
                    (left_wrist.y + right_wrist.y) / 2]
    shoulder_center = [(left_shoulder.x + right_shoulder.x) / 2,
                       (left_shoulder.y + right_shoulder.y) / 2]
    hip_center = [(left_hip.x + right_hip.x) / 2,
                  (left_hip.y + right_hip.y) / 2]
    ankle_center = [(left_ankle.x + right_ankle.x) / 2,
                    (left_ankle.y + right_ankle.y) / 2]

    # 1. 检查臀部是否高于肩膀和脚踝（形成倒V形）
    hip_highest = (hip_center[1] < shoulder_center[1] and
                   hip_center[1] < ankle_center[1])

    # 2. 检查手臂是否伸直
    left_arm_angle = calculate_angle(left_shoulder, left_elbow, left_wrist)
    right_arm_angle = calculate_angle(right_shoulder, right_elbow, right_wrist)

    # 3. 检查腿部是否伸直
    left_leg_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_leg_angle = calculate_angle(right_hip, right_knee, right_ankle)

    # 4. 检查背部是否平直（肩膀到臀部）
    # 计算肩膀中心到臀部中心的向量
    back_angle = abs(shoulder_center[0] - hip_center[0])

    # 判断标准：臀部最高，手臂和腿部接近伸直，背部平直
    is_standard = (hip_highest and
                   left_arm_angle > 160 and
                   right_arm_angle > 160 and
                   left_leg_angle > 160 and
                   right_leg_angle > 160)

    return is_standard


# 战士一式检测函数
def check_warrior_i_pose(landmarks):
    """
    检测战士一式姿势是否标准
    标准战士一式：前腿弯曲90度，后腿伸直，身体直立，手臂上举
    """
    # 获取关键点
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]

    # 确定前腿（弯曲的腿）
    if left_knee.x < right_knee.x:  # 左膝更靠左，左腿在前
        front_leg = "LEFT"
        front_knee = left_knee
        front_ankle = left_ankle
        front_hip = left_hip
        back_knee = right_knee
        back_ankle = right_ankle
    else:
        front_leg = "RIGHT"
        front_knee = right_knee
        front_ankle = right_ankle
        front_hip = right_hip
        back_knee = left_knee
        back_ankle = left_ankle

    # 1. 检查前腿弯曲角度（应为90度左右）
    front_knee_angle = calculate_angle(front_hip, front_knee, front_ankle)

    # 2. 检查后腿是否伸直
    if front_leg == "LEFT":
        back_hip = right_hip
    else:
        back_hip = left_hip
    back_knee_angle = calculate_angle(back_hip, back_knee, back_ankle)

    # 3. 检查前膝盖是否在脚踝正上方（垂直对齐）
    knee_ankle_alignment = abs(front_knee.x - front_ankle.x)

    # 4. 检查身体是否直立（肩膀中心在髋部中心正上方）
    shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
    hip_center_x = (left_hip.x + right_hip.x) / 2
    vertical_alignment = abs(shoulder_center_x - hip_center_x)

    # 5. 检查手臂是否上举（手腕在肩膀上方）
    wrists_above_shoulders = (left_wrist.y < left_shoulder.y and
                              right_wrist.y < right_shoulder.y)

    # 判断标准：前腿90度，后腿伸直，膝盖对齐，身体直立，手臂上举
    is_standard = (75 < front_knee_angle < 105 and
                   back_knee_angle > 170 and
                   knee_ankle_alignment < 0.05 and
                   vertical_alignment < 0.04 and
                   wrists_above_shoulders)
#
    return is_standard
#
#
# 检测侧角伸展式
def check_extended_side_angle_pose(landmarks):
    """
    检测侧角伸展式(Extended Side Angle Pose)是否标准
    标准姿势：
    1. 前腿弯曲90度，膝盖在脚踝正上方
    2. 后腿伸直
    3. 身体向前腿侧弯曲，躯干与地面平行
    4. 下侧手臂接触地面或小腿，上侧手臂伸直与躯干成直线
    """
    # 获取关键点
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_elbow = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
    right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
#
    # 1. 确定前腿（弯曲的腿）
    # 通过比较膝盖位置和弯曲角度
    left_knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_knee_angle = calculate_angle(right_hip, right_knee, right_ankle)
#
    # 判断前腿的标准：弯曲角度接近90度
    is_left_bent = 75 < left_knee_angle < 105
    is_right_bent = 75 < right_knee_angle < 105
#
    # 如果只有一条腿弯曲，则确定为前腿
    if is_left_bent and not is_right_bent:
        front_leg = "LEFT"
    elif is_right_bent and not is_left_bent:
        front_leg = "RIGHT"
    else:
        # 如果两条腿都弯曲或都不弯曲，使用位置判断（膝盖更靠前的为前腿）
        if left_knee.x < right_knee.x:  # 左膝更靠左
            front_leg = "LEFT"
        else:
            front_leg = "RIGHT"
#
    # 根据前腿设置相关点
    if front_leg == "LEFT":
        front_knee = left_knee
        front_ankle = left_ankle
        front_hip = left_hip
        back_knee = right_knee
        back_ankle = right_ankle
        back_hip = right_hip
        lower_arm_wrist = left_wrist  # 下侧手臂（前腿同侧）
        upper_arm_wrist = right_wrist  # 上侧手臂
    else:
        front_knee = right_knee
        front_ankle = right_ankle
        front_hip = right_hip
        back_knee = left_knee
        back_ankle = left_ankle
        back_hip = left_hip
        lower_arm_wrist = right_wrist
        upper_arm_wrist = left_wrist
#
    # 2. 检查前腿弯曲角度
    front_knee_angle = calculate_angle(front_hip, front_knee, front_ankle)
    front_leg_bent = 75 < front_knee_angle < 105
#
    # 3. 检查前膝盖是否在脚踝正上方
    knee_ankle_alignment = abs(front_knee.x - front_ankle.x)
    knee_aligned = knee_ankle_alignment < 0.05
#
    # 4. 检查后腿是否伸直
    back_knee_angle = calculate_angle(back_hip, back_knee, back_ankle)
    back_leg_straight = back_knee_angle > 170
#
    # 5. 检查身体侧弯角度
    # 计算髋部中心
    hip_center = ((left_hip.x + right_hip.x) / 2,
                  (left_hip.y + right_hip.y) / 2)
#
    # 计算肩膀中心
    shoulder_center = ((left_shoulder.x + right_shoulder.x) / 2,
                       (left_shoulder.y + right_shoulder.y) / 2)
#
    # 计算身体弯曲角度（髋中心-肩中心连线与垂直线的夹角）
    dx = shoulder_center[0] - hip_center[0]
    dy = shoulder_center[1] - hip_center[1]
#
    # 计算与垂直线的夹角（垂直线的角度为90度）
    body_angle = math.degrees(math.atan2(dx, dy)) - 90
    body_bent = abs(body_angle) > 45  # 身体倾斜超过45度
#
    # 6. 检查手臂位置
    # 下侧手臂应接近地面（手腕在膝盖下方）
    lower_arm_down = lower_arm_wrist.y > front_knee.y
#
    # 7. 检查手臂与躯干形成的直线
    # 理想情况下，从下臂手腕经躯干到上臂手腕应接近直线
    # 计算三个点：下臂手腕、前腿同侧髋部、上臂手腕
    alignment_angle = calculate_angle(
        lower_arm_wrist,
        front_hip,
        upper_arm_wrist
    )
    body_alignment = 160 < alignment_angle < 200  # 接近180度
#
    # 综合判断标准
    is_standard = (
            front_leg_bent and
            knee_aligned and
            back_leg_straight and
            body_bent and
            lower_arm_down and
            body_alignment
    )
#
    return is_standard
#
#
# 动作检测界面
class PoseDetectionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
#
        # 动作名称映射
        self.pose_names = {
            "tree": "树式 (Tree Pose)",
            "downward_dog": "下犬式 (Downward Dog)",
            "warrior_i": "战士一式 (Warrior I)",
            "side_angle": "侧角伸展式 (Side Angle)"
        }
#
        # 检测函数映射
        self.detection_functions = {
            "tree": check_tree_pose,
            "downward_dog": check_downward_dog,
            "warrior_i": check_warrior_i_pose,
            "side_angle": check_extended_side_angle_pose
        }
#
        self.setup_ui()
#
        # 添加退出按钮（根据语言切换文案）
        exit_text = "Exit" if language == "EN" else "退出系统"
        exit_btn = QPushButton(exit_text)
        exit_btn.setFont(QFont("Arial", 12))
        exit_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border-radius: 5px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            """
        )
        exit_btn.clicked.connect(self.close_app)
        self.layout().addWidget(exit_btn, alignment=Qt.AlignCenter)
#
    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
#
        # 标题（根据语言切换文案）
        title_text = "Real-time Yoga Movement Detection System" if language == "EN" else "瑜伽动作实时检测系统"
        title = QLabel(title_text)
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        layout.addWidget(title)
#
        # 图像显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(1280, 720)  # 高清显示
        self.image_label.setStyleSheet("background-color: black; border-radius: 10px;")
        layout.addWidget(self.image_label, 1)
#
        # 检测结果区域
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(20, 20, 20, 20)
        result_container.setStyleSheet("""
            background-color: #f8f9fa;
            border-radius: 10px;
            border: 2px solid #3498db;
        """)
#
        # 当前动作标题（根据语言切换文案）
        action_title_text = "Currently detected action:" if language == "EN" else "当前检测到的动作:"
        action_title = QLabel(action_title_text)
        action_title.setFont(QFont("Arial", 14, QFont.Bold))
        action_title.setStyleSheet("color: #2c3e50;")
        result_layout.addWidget(action_title, alignment=Qt.AlignCenter)
#
        # 动作名称显示
        self.detected_action = QLabel("等待检测...")
        self.detected_action.setFont(QFont("Arial", 18, QFont.Bold))
        self.detected_action.setStyleSheet("color: #e74c3c; margin-top: 10px; margin-bottom: 20px;")
        result_layout.addWidget(self.detected_action, alignment=Qt.AlignCenter)
#
        # 状态信息
        self.status_label = QLabel("系统状态: 正在初始化...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setStyleSheet("color: #7f8c8d;")
        result_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)
#
        layout.addWidget(result_container)
#
        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)
#
    def update_frame(self):
        success, image = self.cap.read()
        if not success:
            self.status_label.setText("系统状态: 无法读取摄像头画面")
            return
#
        # 转换为RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.pose.process(image_rgb)
        image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
#
        detected_pose = "No action detected" if language == "EN" else "未检测到动作"
        pose_correct = False
#
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            image_height, image_width, _ = image.shape
#
            # 检测所有姿势
            for pose_id, detection_func in self.detection_functions.items():
                if detection_func(landmarks):
                    detected_pose = self.pose_names[pose_id]
                    pose_correct = True
                    break  # 只显示第一个检测到的姿势
#
            # 更新状态标签
            self.detected_action.setText(detected_pose)
            if detected_pose != ("No action detected" if language == "EN" else "未检测到动作"):
                self.status_label.setText(
                    f"系统状态: 检测到 {detected_pose.split(' ')[0]} - {'动作标准' if pose_correct else '动作不标准'}")
                color = (0, 255, 0) if pose_correct else (0, 165, 255)  # 标准为绿色，不标准为橙色
                self.detected_action.setStyleSheet(f"color: {'#2ecc71' if pose_correct else '#e67e22'};")
            else:
                status_text = (
                    "System status: No standard yoga poses detected."
                    if language == "EN"
                    else "系统状态: 未检测到标准瑜伽动作"
                )
                self.status_label.setText(status_text)
                self.detected_action.setStyleSheet("color: #e74c3c;")
#
            # 在图像上显示检测结果
            cv2.putText(image, detected_pose, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (0, 0, 255)
                        if detected_pose == ("No action detected" if language == "EN" else "未检测到动作")
                        else color,
                        2, cv2.LINE_AA)
#
            # 绘制自定义骨骼
            for connection in CUSTOM_CONNECTIONS:
                start_idx = connection[0].value
                end_idx = connection[1].value
                start = landmarks[start_idx]
                end = landmarks[end_idx]
#
                # 转换为像素坐标
                start_x = int(start.x * image_width)
                start_y = int(start.y * image_height)
                end_x = int(end.x * image_width)
                end_y = int(end.y * image_height)
#
                # 绘制连接线
                cv2.line(image, (start_x, start_y), (end_x, end_y), (0, 0, 255), 3)
                # 绘制关节点
                cv2.circle(image, (start_x, start_y), 8, (0, 255, 0), -1)
                cv2.circle(image, (end_x, end_y), 8, (0, 255, 0), -1)
#
        # 显示图像
        height, width, _ = image.shape
        bytes_per_line = 3 * width
        q_img = QImage(image.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        self.image_label.setPixmap(QPixmap.fromImage(q_img))
#
    def close_app(self):
        self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        if hasattr(self, 'pose'):
            self.pose.close()
        QApplication.quit()
#
    def closeEvent(self, event):
        self.close_app()
        event.accept()
#
#
# 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("瑜伽动作实时检测系统")
        self.setGeometry(100, 100, 1400, 900)
#
        # 设置窗口图标
        # self.setWindowIcon(QIcon("yoga_icon.png"))
#
        # 创建检测窗口
        self.detection_window = PoseDetectionWindow()
        self.setCentralWidget(self.detection_window)
#
#
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lang",
        choices=["CN", "EN"],
        default="CN",
        help="Language for UI labels and messages. Supported values: CN, EN. Default: CN.",
    )
    args = parser.parse_args()

    # 设置全局语言变量
    language = args.lang

    app = QApplication(sys.argv)
#
    # 设置应用程序样式
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget {
            background-color: #ecf0f1;
            font-family: Arial;
        }
        QLabel {
            color: #2c3e50;
        }
        QPushButton {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 14px;
            min-width: 100px;
        }
        QPushButton:hover {
            background-color: #2980b9;
        }
        QMessageBox {
            background-color: white;
        }
    """)
#
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
