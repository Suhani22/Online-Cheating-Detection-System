from flask import Flask, render_template, Response, jsonify
import cv2
from ultralytics import YOLO
import time

face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
alert_message = "No Alert"
last_yolo_time = 0
warning_count = 0
max_warnings = 5
exam_terminated = False
last_alert_time = 0
cooldown = 3   # seconds (avoid multiple counts per second)
last_phone_detected = False

# ✅ FIRST define app
app = Flask(__name__)

# Load model and camera
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(0)

# ---------------- ROUTES ---------------- #
@app.route('/alert')
def get_alert():
    return jsonify({"alert": alert_message})

@app.route('/status')
def status():
    return jsonify({
        "warnings": warning_count,
        "terminated": exam_terminated
    })

@app.route('/tab_switch')
def tab_switch():
    global alert_message, cap, warning_count, exam_terminated, last_alert_time, last_yolo_time, last_phone_detected

    current_time = time.time()

    if not exam_terminated:
        if current_time - last_alert_time > cooldown:
            warning_count += 1
            last_alert_time = current_time

            print("Tab switched → warning")

            if warning_count >= max_warnings:
                exam_terminated = True

    return "OK"

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/test")
def test():
    return render_template("test.html")

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

# ---------------- VIDEO STREAM ---------------- #

def generate_frames():
    global alert_message, cap, warning_count, exam_terminated, last_alert_time,  last_yolo_time, last_phone_detected

    if not cap.isOpened():
        cap = cv2.VideoCapture(0)

    try:
        while True:
            success, frame = cap.read()
            if not success:
                break

            if exam_terminated:
                cv2.putText(frame, "EXAM TERMINATED", (50,200),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                continue

            # 🔹 Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 🔹 Face detection (ONLY frontal)
            faces = face_cascade.detectMultiScale(gray,
                scaleFactor=1.2,    
                minNeighbors=5,     
                minSize=(60, 60))
            face_count = len(faces)

            valid_faces = []

            for (x, y, w, h) in faces:
                if w > 60 and h > 60:
                    valid_faces.append((x, y, w, h))

            face_count = len(valid_faces)

            looking_away = False
            for (x, y, w, h) in valid_faces:
                cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
                # 🔹 Head movement detection
                frame_center = frame.shape[1] // 2

                for (x, y, w, h) in valid_faces:

                    face_center = x + w // 2

    # If face moves too much left/right
                    if abs(face_center - frame_center) > 120:
                        looking_away = True

            # 🔹 YOLO detection
            current_time = time.time()

            if current_time - last_yolo_time > 0.5:
                results = model(frame)

                phone_detected = False

                for r in results:
                    for box in r.boxes:
                        class_id = int(box.cls[0])
                        confidence = float(box.conf[0])

                        if class_id == 67 and confidence > 0.4:
                            phone_detected = True

                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cv2.rectangle(frame, (x1,y1), (x2,y2), (255,0,0), 2)
                            cv2.putText(frame, "PHONE", (x1,y1-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)

                last_phone_detected = phone_detected
                last_yolo_time = current_time

            phone_detected = last_phone_detected


            # 🔴 ALERT + WARNING LOGIC
            current_time = time.time()

            alert_message = "No Alert"

            if face_count > 1:
                alert_message = "Multiple Faces "

            elif phone_detected:
                alert_message = "Phone Detected"

            elif looking_away:
                alert_message = "Looking Away Detected"
            

            # 🔥 WARNING COUNT SYSTEM
            if (face_count > 1 or phone_detected or looking_away) and not exam_terminated:
                if current_time - last_alert_time > cooldown:
                    warning_count += 1
                    last_alert_time = current_time

                    print(f"Warning {warning_count}/{max_warnings}")

                    if warning_count >= max_warnings:
                        exam_terminated = True
                        alert_message = "Exam Terminated"


            if alert_message == "":
                alert_message = "No Alert"

            # 🔹 Convert frame
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    except GeneratorExit:
        print("Client disconnected → releasing camera")
        cap.release()

# ✅ NOW app is defined, so this works
@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stop_camera')
def stop_camera():
    global cap
    if cap.isOpened():
        cap.release()
    return "Camera Stopped"

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(debug=True)