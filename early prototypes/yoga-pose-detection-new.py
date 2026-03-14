
# 这一版实现了根据用户的动作去反应到底检查到了何种动作
import cv2
import mediapipe as mp
import math
import sys
import os
import argparse
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                             QPushButton, QMessageBox, QMainWindow, QFrame)
from PyQt5.QtGui import QImage, QPixmap, QFont, QIcon, QColor, QPalette
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
# 姿势卡片组件
class PoseCard(QFrame):
    """视觉姿势卡片，当检测到姿势时高亮显示"""

    def __init__(self, pose_key: str, display_name: str, image_path: str | None = None, parent=None):
        super().__init__(parent)
        self.pose_key = pose_key
        self.display_name = display_name
        self.image_path = image_path

        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(2)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title_label = QLabel(display_name)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Arial", 14, QFont.Bold))

        self.image_label = QLabel()
        # 预览区域为正方形以匹配方形姿势参考图像
        self.image_label.setFixedSize(160, 160)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: #ecf0f1; border-radius: 6px; color: #7f8c8d;"
        )

        # 如果提供了预览图像则加载，否则显示占位符文本
        if self.image_path and os.path.exists(self.image_path):
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                self.image_label.setPixmap(
                    pix.scaled(
                        self.image_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            else:
                self.image_label.setText("Pose\npreview")
        else:
            self.image_label.setText("Pose\npreview")

        self.status_label = QLabel("Not detected" if language == "EN" else "未检测到")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 10))

        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.status_label)

        self.set_inactive_style()

    def set_active(self, is_active: bool):
        if is_active:
            self.set_active_style()
            self.status_label.setText("Detected" if language == "EN" else "检测到")
        else:
            self.set_inactive_style()
            self.status_label.setText("Not detected" if language == "EN" else "未检测到")

    def set_active_style(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#e8f8f5"))
        self.setPalette(palette)
        self.setStyleSheet(
            "QFrame { border: 2px solid #1abc9c; border-radius: 8px; }"
        )
        self.title_label.setStyleSheet("color: #16a085;")

    def set_inactive_style(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#ffffff"))
        self.setPalette(palette)
        self.setStyleSheet(
            "QFrame { border: 1px solid #bdc3c7; border-radius: 8px; }"
        )
        self.title_label.setStyleSheet("color: #2c3e50;")


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
        # 姿势显示名称（双语，用于卡片标题）
        self.pose_display_names = {
            "tree": "树式 (Tree Pose)",
            "downward_dog": "下犬式 (Downward Dog)",
            "warrior_i": "战士一式 (Warrior I)",
            "side_angle": "侧角伸展式 (Side Angle)"
        }
#
        # 姿势预览图像路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        poses_dir = os.path.join(base_dir, "pose_images")
        self.pose_image_paths = {
            "tree": os.path.join(poses_dir, "tree.png"),
            "downward_dog": os.path.join(poses_dir, "downward_dog.png"),
            "warrior_i": os.path.join(poses_dir, "warrior_i.png"),
            "side_angle": os.path.join(poses_dir, "side_angle.png"),
        }
#
        # 当前检测到的姿势键
        self.current_pose_key = "none"
#
        self.setup_ui()
#
    def setup_ui(self):
        # 主水平布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
#
        # 左侧：视频区域
        video_container = QFrame()
        video_container.setFrameShape(QFrame.NoFrame)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(12)
#
        # 标题（根据语言切换文案）
        title_text = "Real-time Yoga Movement Detection System" if language == "EN" else "瑜伽动作实时检测系统"
        title = QLabel(title_text)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("color: #2c3e50;")
        video_layout.addWidget(title)
#
        # 视频显示区域（重命名为video_label）
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(960, 540)  # 响应式最小尺寸
        self.video_label.setStyleSheet("background-color: black; border-radius: 10px;")
        video_layout.addWidget(self.video_label, 1)
#
        # 视频状态标签
        self.video_status_label = QLabel("No pose detected" if language == "EN" else "未检测到动作")
        self.video_status_label.setAlignment(Qt.AlignCenter)
        self.video_status_label.setFont(QFont("Arial", 14))
        self.video_status_label.setStyleSheet("color: #e67e22; font-weight: 500; margin-top: 4px;")
        video_layout.addWidget(self.video_status_label)
#
        # 右侧：侧边栏面板
        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #dfe4ea;
            }
        """)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(16)
#
        # 侧边栏标题（根据语言切换文案）
        side_title_text = "Pose Guide & Status" if language == "EN" else "体式指南与状态"
        side_title = QLabel(side_title_text)
        side_title.setFont(QFont("Arial", 16, QFont.Bold))
        side_title.setAlignment(Qt.AlignCenter)
        side_title.setStyleSheet("color: #2c3e50;")
        side_layout.addWidget(side_title)
#
        # 姿势卡片
        self.pose_cards = {}
        for key, name in self.pose_display_names.items():
            card = PoseCard(key, name, self.pose_image_paths.get(key))
            self.pose_cards[key] = card
            side_layout.addWidget(card)
#
        # 检测结果区域（保留原有功能）
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(12, 12, 12, 12)
        result_container.setStyleSheet("""
            background-color: #ffffff;
            border-radius: 8px;
            border: 1px solid #bdc3c7;
        """)
#
        # 当前动作标题（根据语言切换文案）
        action_title_text = "Currently detected action:" if language == "EN" else "当前检测到的动作:"
        action_title = QLabel(action_title_text)
        action_title.setFont(QFont("Arial", 12, QFont.Bold))
        action_title.setStyleSheet("color: #2c3e50;")
        result_layout.addWidget(action_title, alignment=Qt.AlignCenter)
#
        # 动作名称显示
        self.detected_action = QLabel("等待检测..." if language == "EN" else "等待检测...")
        self.detected_action.setFont(QFont("Arial", 14, QFont.Bold))
        self.detected_action.setStyleSheet("color: #e74c3c; margin-top: 8px; margin-bottom: 8px;")
        result_layout.addWidget(self.detected_action, alignment=Qt.AlignCenter)
#
        # 状态信息
        init_status_text = "System status: Initializing..." if language == "EN" else "系统状态: 正在初始化..."
        self.status_label = QLabel(init_status_text)
        self.status_label.setFont(QFont("Arial", 11))
        self.status_label.setStyleSheet("color: #7f8c8d;")
        result_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)
#
        side_layout.addWidget(result_container)
        side_layout.addStretch(1)
#
        # 退出按钮（根据语言切换文案）
        exit_text = "Exit" if language == "EN" else "退出系统"
        exit_btn = QPushButton(exit_text)
        exit_btn.setFont(QFont("Arial", 12))
        exit_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """
        )
        exit_btn.clicked.connect(self.close_app)
        side_layout.addWidget(exit_btn, alignment=Qt.AlignCenter)
#
        # 将左右两部分添加到主布局
        main_layout.addWidget(video_container, 3)  # 视频区域占3份
        main_layout.addWidget(side_panel, 1)  # 侧边栏占1份
#
        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)
#
    def update_detected_pose(self, pose_key: str, pose_correct: bool):
        """更新检测到的姿势视觉效果"""
        # 规范化姿势键
        if pose_key not in {"tree", "downward_dog", "warrior_i", "side_angle", "none"}:
            pose_key = "none"
#
        self.current_pose_key = pose_key
#
        # 更新视频状态标签
        if pose_key == "none":
            no_pose_text = "No pose detected" if language == "EN" else "未检测到动作"
            self.video_status_label.setText(no_pose_text)
            self.video_status_label.setStyleSheet(
                "color: #e67e22; font-weight: 500; margin-top: 4px;"
            )
        else:
            pose_name = self.pose_display_names.get(pose_key, "Unknown pose")
            detected_text = f"Detected: {pose_name}" if language == "EN" else f"检测到: {pose_name}"
            self.video_status_label.setText(detected_text)
            if pose_correct:
                self.video_status_label.setStyleSheet(
                    "color: #27ae60; font-weight: 600; margin-top: 4px;"
                )
            else:
                self.video_status_label.setStyleSheet(
                    "color: #e67e22; font-weight: 600; margin-top: 4px;"
                )
#
        # 更新检测到的动作标签
        if pose_key == "none":
            no_action_text = "No action detected" if language == "EN" else "未检测到动作"
            self.detected_action.setText(no_action_text)
            self.detected_action.setStyleSheet("color: #e74c3c; margin-top: 8px; margin-bottom: 8px;")
        else:
            pose_name = self.pose_names.get(pose_key, "Unknown")
            self.detected_action.setText(pose_name)
            if pose_correct:
                self.detected_action.setStyleSheet("color: #2ecc71; margin-top: 8px; margin-bottom: 8px;")
            else:
                self.detected_action.setStyleSheet("color: #e67e22; margin-top: 8px; margin-bottom: 8px;")
#
        # 更新状态标签
        if pose_key == "none":
            status_text = (
                "System status: No standard yoga poses detected."
                if language == "EN"
                else "系统状态: 未检测到标准瑜伽动作"
            )
            self.status_label.setText(status_text)
        else:
            pose_name_short = self.pose_names[pose_key].split(' ')[0]
            if language == "EN":
                status_text = f"System status: Detected {pose_name_short} - {'Standard pose' if pose_correct else 'Non-standard pose'}"
            else:
                status_text = f"系统状态: 检测到 {pose_name_short} - {'动作标准' if pose_correct else '动作不标准'}"
            self.status_label.setText(status_text)
#
        # 更新姿势卡片高亮
        for key, card in self.pose_cards.items():
            card.set_active(key == pose_key)
#
    def update_frame(self):
        success, image = self.cap.read()
        if not success:
            error_text = "System status: Unable to read camera feed" if language == "EN" else "系统状态: 无法读取摄像头画面"
            self.status_label.setText(error_text)
            return
#
        # 转换为RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.pose.process(image_rgb)
        image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
#
        detected_pose_key = "none"
        pose_correct = False
        color = (0, 0, 255)  # 默认红色（无检测）
#
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            image_height, image_width, _ = image.shape
#
            # 检测所有姿势
            for pose_id, detection_func in self.detection_functions.items():
                if detection_func(landmarks):
                    detected_pose_key = pose_id
                    pose_correct = True
                    break  # 只显示第一个检测到的姿势
#
            # 准备在图像上显示的文本和颜色
            if detected_pose_key != "none":
                detected_pose_text = self.pose_names[detected_pose_key]
                color = (0, 255, 0) if pose_correct else (0, 165, 255)  # 标准为绿色，不标准为橙色
            else:
                detected_pose_text = "No action detected" if language == "EN" else "未检测到动作"
                color = (0, 0, 255)  # 红色
#
            # 在图像上显示检测结果
            cv2.putText(image, detected_pose_text, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2, cv2.LINE_AA)
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
        # 更新视觉效果（在所有情况下都调用）
        self.update_detected_pose(detected_pose_key, pose_correct)
#
        # 显示图像（使用video_label）
        height, width, _ = image.shape
        bytes_per_line = 3 * width
        q_img = QImage(image.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        # 缩放图像以适应标签大小，保持宽高比
        # 如果标签尚未调整大小，使用图像原始尺寸
        label_width = self.video_label.width() if self.video_label.width() > 0 else width
        label_height = self.video_label.height() if self.video_label.height() > 0 else height
        scaled = q_img.scaled(
            label_width,
            label_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(QPixmap.fromImage(scaled))
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
        window_title = "Real-time Yoga Movement Detection System" if language == "EN" else "瑜伽动作实时检测系统"
        self.setWindowTitle(window_title)
        # 响应式窗口大小，可根据屏幕调整
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 700)  # 设置最小尺寸以支持响应式布局
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
