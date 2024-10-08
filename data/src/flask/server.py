import os
import requests
from flask import (
    Flask,
    request,
    send_file,
    render_template,
    jsonify,
    Response,
    redirect,
    url_for,
)
from io import BytesIO
import scipy.io.wavfile as swavfile

from synthesys import SAMPLING_RATE
from synthesys import generate_audio_glow_tts
from text_processer import normalize_text, process_text

app = Flask(__name__)


@app.after_request
def allow_cors(response):
    response.headers['Access-Control-Allow-Origin'] = "*"
    return response


@app.route("/")
def index():
    return redirect(url_for("text_inference"))


@app.route("/tts-server/text-inference")
def text_inference():
    return render_template("text-inference.html")


@app.route("/tts-server/cc-overlay")
def open_captions_overlay():
    return render_template("cc-overlay.html")


@app.route("/tts-server/api/process-text", methods=["POST"])
def text():
    text = request.json.get("text", "")
    texts = process_text(text)

    return jsonify(texts)


@app.route("/tts-server/api/infer-glowtts", methods=["GET", "POST"])
def infer_glowtts():
    
    if request.method == "POST":
        # POST 요청일 경우 JSON 또는 폼 데이터에서 텍스트 받기
        data = request.get_json()
        if data and 'text' in data:
            text = data['text']
        else:
            return "No text provided in POST request", 400
    else:
        # GET 요청일 경우 쿼리 파라미터에서 텍스트 받기
        text = request.args.get("text", "")
    
    # 텍스트를 정상화
    text = normalize_text(text).strip()

    if not text:
        return "Text shouldn't be empty", 400

    try:
        # TTS 음성 생성
        wav = synthesize(text)
        return send_file(wav, mimetype="audio/wav", download_name="audio.wav")  # Flask 2.1에서는 attachment_filename 대신 download_name 사용
    except Exception as e:
        return f"Cannot generate audio: {str(e)}", 500


@app.route("/favicon.ico")
def favicon():
    return "I don't have favicon :p", 404


@app.route("/<path:path>")
def twip_proxy(path):
    new_url = request.url.replace(request.host, "twip.kr")
    resp = requests.request(
        method=request.method,
        url=new_url,
        headers={key: value for (key, value) in request.headers if key != "Host"},
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
    )
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]
    headers = [
        (name, value)
        for (name, value) in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    ]
    content = resp.content
    if new_url.startswith("http://twip.kr/assets/js/alertbox/lib-"):
        content = (
            resp.text
            + f"""
        const original_function = Howl.prototype.init;
        Howl.prototype.init = function (o) {{
            if (o.src.startsWith('https://www.google.com/speech-api/v1/synthesize?text=')) {{
                o.src = o.src.replace(
                    'https://www.google.com/speech-api/v1/synthesize?text=',
                    '/tts-server/api/infer-glowtts?text='
                );
                o.html5 = false;
                o.volume = o.volume * 2;
            }}
            return original_function.call(this, o);
        }}
        """
        )
    response = Response(content, resp.status_code, headers)
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=os.environ.get("TTS_DEBUG", "0") == "1")
