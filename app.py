from flask import Flask, request, jsonify, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_httpauth import HTTPBasicAuth
import base64
import json
import requests
from PIL import Image, ImageDraw, ImageFont
import os
from werkzeug.utils import secure_filename
import logging
import sys
import threading
import backoff
from uuid import uuid4
from threading import Thread
import time
import shutil

print("Flask application starting...")

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

handler_out = logging.StreamHandler(sys.stdout)
handler_err = logging.StreamHandler(sys.stderr)
handler_out.setLevel(logging.DEBUG)
handler_err.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler_out.setFormatter(formatter)
handler_err.setFormatter(formatter)
app.logger.addHandler(handler_out)
app.logger.addHandler(handler_err)
app.logger.info('Logging setup complete - test log entry.')

ollama_lock = threading.Lock()

UPLOAD_FOLDER = '/home/ubuntu/MemeGenBackend/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Global dictionary to store job statuses and a lock for thread-safe operations
jobs = {}
jobs_lock = threading.Lock()

# Instantiate Limiter for rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["1 per second"])
limiter.init_app(app)

# Instantiate HTTPBasicAuth for authentication
auth = HTTPBasicAuth()

# Define the verification function for HTTPBasicAuth
@auth.verify_password
def verify_password(username, password):
    return username == 'admin' and password == 'password'

def process_meme_generation(file_path, job_id, filename):
    try:
        app.logger.debug(f"Starting meme text generation for job_id: {job_id}")
        meme_text = generate_meme(file_path)
        app.logger.debug(f"Meme text generation completed for job_id: {job_id}, result: {meme_text}")
        if meme_text:
            app.logger.debug(f"Starting overlay meme text for job_id: {job_id}")
            image_with_meme = overlay_meme_text(file_path, meme_text)
            app.logger.debug(f"Overlay meme text completed for job_id: {job_id}")
            # Create a subdirectory for the job_id within the uploads folder
            job_folder = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
            os.makedirs(job_folder, exist_ok=True)
            output_path = os.path.join(job_folder, f'meme_{filename}')
            app.logger.debug(f"Saving meme image for job_id: {job_id} to {output_path}")
            image_with_meme.save(output_path)
            app.logger.debug(f"Meme image saved to {output_path} for job_id: {job_id}")
            with jobs_lock:
                app.logger.debug(f"Before updating job status to 'completed', current job info: {jobs.get(job_id, 'Job ID not found')}")
                jobs[job_id] = {'status': 'completed', 'meme_image_path': output_path, 'completed_time': time.time()}
                app.logger.debug(f"After updating job status to 'completed', new job info: {jobs[job_id]}")
        else:
            app.logger.debug(f"meme_text is None or empty for job_id: {job_id}")
            with jobs_lock:
                jobs[job_id] = {'status': 'failed', 'error': 'Failed to generate meme text'}
    except Exception as e:
        app.logger.error(f"Exception in process_meme_generation function for job_id: {job_id}, error: {e}")
        with jobs_lock:
            jobs[job_id] = {'status': 'failed', 'error': str(e)}

@app.route('/upload', methods=['POST'])
def upload_file():
    app.logger.debug("Received request at /upload endpoint")
    app.logger.debug("Starting upload_file function")
    if 'file' not in request.files:
        app.logger.debug("No file part in request")
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    app.logger.debug(f"Type of file object: {type(file)}")
    if file.filename == '':
        app.logger.debug("No file selected")
        return jsonify({'error': 'No selected file'}), 400
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        app.logger.debug(f"File {filename} saved to {file_path}")
        # Generate a unique job identifier
        job_id = str(uuid4())
        # Start the meme generation process in a background thread
        thread = Thread(target=process_meme_generation, args=(file_path, job_id, filename))
        thread.start()
        # Store the initial job status
        with jobs_lock:
            jobs[job_id] = {'status': 'in_progress'}
        # Return the job identifier to the user
        return jsonify({'job_id': job_id}), 202
    app.logger.debug("Ending upload_file function")

# Apply the rate limit and authentication decorators to the `/status` endpoint
@app.route('/status/<job_id>', methods=['GET'])
@limiter.limit("1 per second")
@auth.login_required
def get_status(job_id):
    app.logger.debug(f"Received request at /status endpoint for job_id: {job_id}")
    # Check if the job_id exists in the jobs dictionary
    with jobs_lock:
        if job_id in jobs:
            job_info = jobs[job_id]
            # If the job is completed, return the job status without serving the image file
            if job_info['status'] == 'completed':
                return jsonify({'status': 'completed'}), 200
            else:
                # If the job is not completed, return the job status
                return jsonify(job_info), 200
        else:
            # If the job_id does not exist, return an error message
            return jsonify({'error': 'Job not found'}), 404

@app.route('/result/<job_id>', methods=['GET'])
@auth.login_required
def get_result(job_id):
    app.logger.debug(f"Received request at /result endpoint for job_id: {job_id}")
    # Check if the job_id exists in the jobs dictionary and if the job is completed
    with jobs_lock:
        job_info = jobs.get(job_id)
        if job_info and job_info['status'] == 'completed':
            meme_image_path = job_info['meme_image_path']
            if os.path.exists(meme_image_path):
                return send_file(meme_image_path, mimetype='image/jpeg')
            else:
                return jsonify({'error': 'Meme image not found'}), 404
        elif job_info and job_info['status'] != 'completed':
            return jsonify({'error': 'Job is not completed'}), 202
        else:
            return jsonify({'error': 'Job not found'}), 404

@backoff.on_exception(backoff.expo,
                      requests.exceptions.RequestException,
                      max_tries=5,
                      giveup=lambda e: e.response is not None and e.response.status_code < 500)
def send_request_with_backoff(url, payload, headers):
    return requests.post(url, data=json.dumps(payload), headers=headers, timeout=180)

def generate_meme(image_path):
    app.logger.debug(f"Generating meme for image: {image_path}")
    ollama_url = 'http://ollama:11434/api/generate'
    try:
        with ollama_lock:
            with open(image_path, 'rb') as image_file:
                try:
                    image_data = image_file.read()
                    app.logger.debug(f"Read image data length: {len(image_data)}")
                    encoded_image = base64.b64encode(image_data).decode('utf-8')
                    app.logger.debug(f"Encoded image data length: {len(encoded_image)}")
                except Exception as e:
                    app.logger.error(f"Exception during image read or base64 encoding: {e}")
                    raise
                app.logger.debug(f"Full Base64 encoded image data: {encoded_image}")
                payload = {
                    "model": "llava-phi3",
                    "prompt": "Describe this image:",
                    "stream": False,
                    "images": [encoded_image]
                }
                app.logger.debug(f"Full payload: {json.dumps(payload)}")
                headers = {'Content-Type': 'application/json'}
                app.logger.debug(f"Sending request to Ollama service for image analysis: {ollama_url}")
                response = send_request_with_backoff(ollama_url, payload, headers)
                app.logger.debug(f"Response from Ollama service received: Status Code: {response.status_code}, Headers: {response.headers}, Response Body: {response.text}")
                if response.status_code != 200:
                    app.logger.error(f"Error response from Ollama service: Status Code: {response.status_code}, Response Body: {response.text}")
                    return None
                app.logger.debug(f"Ollama service response is OK. Processing response...")
                response_json = response.json()
                if 'response' not in response_json or not isinstance(response_json['response'], str):
                    app.logger.error(f"Ollama service response does not contain 'response' key or it is not a string")
                    app.logger.error(f"Ollama service response content: {response_json}")
                    return None
                description = response_json['response']
                app.logger.debug(f"Image description: {description}")
                return generate_meme_text(description)
    except Exception as e:
        app.logger.error(f"Exception in generate_meme function: {e}")
        if hasattr(e, 'response') and e.response:
            app.logger.error(f"Response content: {e.response.content}")
        return None

def generate_meme_text(description):
    app.logger.debug(f"Generating meme text for description: {description}")
    ollama_url = 'http://ollama:11434/api/generate'
    try:
        payload = {
            "model": "llama3:8b",
            "prompt": f"Create a funny meme with the format 'When {description}, then [something humorous]'.",
            "max_tokens": 60,  # Limit the number of tokens to encourage brevity
            "stream": False,
        }
        headers = {'Content-Type': 'application/json'}
        app.logger.debug(f"Sending request to Ollama service for meme text generation: {ollama_url}")
        app.logger.debug(f"Request headers: {headers}")
        app.logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        response = send_request_with_backoff(ollama_url, payload, headers)
        app.logger.debug(f"Ollama service response status: {response.status_code}")
        app.logger.debug(f"Ollama service response headers: {response.headers}")
        app.logger.debug(f"Ollama service response body: {response.text}")
        if response.status_code != 200:
            app.logger.error(f"Error response from Ollama service for meme text generation: Status Code: {response.status_code}, Response Body: {response.text}")
            return None
        app.logger.debug(f"Ollama service response for meme text generation is OK. Processing response...")
        response_json = response.json()
        app.logger.debug(f"Ollama service response for meme text generation: {response_json}")
        if 'response' not in response_json or not isinstance(response_json['response'], str):
            app.logger.error(f"Ollama service response for meme text generation does not contain 'response' key or it is not a string")
            app.logger.error(f"Ollama service response for meme text generation content: {response_json}")
            return None
        meme_text = response_json['response']
        # Post-process to ensure the text is no more than 20 words
        meme_text_words = meme_text.split()
        if len(meme_text_words) > 20:
            meme_text = ' '.join(meme_text_words[:20])
        return meme_text
    except Exception as e:
        app.logger.error(f"Exception in generate_meme_text function: {e}")
        if hasattr(e, 'response') and e.response:
            app.logger.error(f"Response content: {e.response.content}")
        return None

def overlay_meme_text(image_path, text):
    app.logger.debug(f"Starting text overlay on image: {image_path} with text: {text}")
    try:
        image = Image.open(image_path)
        app.logger.debug(f"Image format: {image.format}, Image mode: {image.mode}, Image size: {image.size}")
        draw = ImageDraw.Draw(image)
        font_size = 45
        min_font_size = 10
        font_path = '/usr/src/app/fonts/dejavu-sans-ttf-2.37/ttf/DejaVuSans.ttf'
        font = ImageFont.truetype(font_path, size=font_size)
        wrapped_text = wrap_text(text, image.size[0], font, draw)
        text_size = draw.multiline_textsize(wrapped_text, font=font)
        app.logger.debug(f"Wrapped text size: {text_size}, Wrapped text: {wrapped_text}")

        # Calculate text position and box dimensions
        text_position = ((image.size[0] - text_size[0]) // 2, (image.size[1] - text_size[1]) // 2)
        box_position = (text_position[0] - 10, text_position[1] - 10, text_position[0] + text_size[0] + 10, text_position[1] + text_size[1] + 10)

        # Draw semi-transparent rectangle behind text
        rectangle_image = Image.new('RGBA', image.size)
        rectangle_draw = ImageDraw.Draw(rectangle_image)
        rectangle_draw.rectangle(box_position, fill=(0, 0, 0, 128))  # Dark rectangle with 50% opacity
        image = Image.alpha_composite(image.convert('RGBA'), rectangle_image)

        # Draw text over the rectangle
        draw = ImageDraw.Draw(image)
        draw.multiline_text(text_position, wrapped_text, font=font, fill=(255, 255, 255), align='center')

        app.logger.debug(f"Text overlay applied successfully for image: {image_path}")
    except Exception as e:
        app.logger.error(f"Unexpected error during text overlay: {e}")
        raise
    return image.convert('RGB')  # Convert back to RGB to save as JPEG

def wrap_text(text, max_width, font, draw):
    lines = []
    words = text.split()
    while words:
        line = ''
        while words:
            word = words[0]
            # Check if the word is wider than the max width and split it if necessary
            while draw.textsize(word, font=font)[0] > max_width:
                # Split the word by half until it fits the max width
                split_index = len(word) // 2
                word = word[:split_index]
            line_width = draw.textsize(line + word, font=font)[0]
            if line_width <= max_width:
                line += (words.pop(0) + ' ')
            else:
                break
        lines.append(line.strip())
    return '\n'.join(lines)

def truncate_text(text, max_height, font, draw):
    """
    Truncate the text to fit within the specified height.

    Args:
        text (str): The text to be truncated.
        max_height (int): The maximum height allowed for the text.
        font (ImageFont): The font used for the text.
        draw (ImageDraw): The drawing context.

    Returns:
        str: The truncated text.
    """
    lines = text.split('\n')
    while lines:
        # Check the total size of the text with the current number of lines
        text_size = draw.multiline_textsize('\n'.join(lines), font=font)
        # If the text height is within the allowed maximum height, we are done
        if text_size[1] <= max_height:
            return '\n'.join(lines)
        # Otherwise, remove the last line and check again
        lines.pop()
    # If all lines are removed and still not fitting, return an empty string
    return ''

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"An unhandled exception occurred: {e}", exc_info=True)
    return jsonify({'error': 'An internal server error occurred'}), 500

def cleanup_jobs_and_files():
    """
    Clean up completed or failed jobs and their associated files.
    """
    app.logger.debug("Starting cleanup of jobs and files")
    jobs_to_remove = []
    current_time = time.time()
    with jobs_lock:
        for job_id, job_info in list(jobs.items()):
            if job_info['status'] in ['completed', 'failed']:
                # Check if enough time has passed before cleanup
                if 'completed_time' in job_info and current_time - job_info['completed_time'] > 3600:  # Extend grace period to 1 hour
                    jobs_to_remove.append(job_id)
                    # Delete the job-specific directory if it exists
                    job_folder = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
                    if os.path.exists(job_folder):
                        try:
                            shutil.rmtree(job_folder)
                            app.logger.debug(f"Deleted job directory: {job_folder}")
                        except OSError as e:
                            app.logger.error(f"Error deleting job directory {job_folder}: {e}")
        # Remove jobs from the dictionary
        for job_id in jobs_to_remove:
            del jobs[job_id]
            app.logger.debug(f"Removed job {job_id} from jobs dictionary")

# Schedule the cleanup function to run periodically
def schedule_cleanup():
    cleanup_interval = 300  # Run cleanup every 5 minutes
    cleanup_thread = threading.Timer(cleanup_interval, schedule_cleanup)
    cleanup_thread.daemon = True  # Daemonize thread
    cleanup_thread.start()
    cleanup_jobs_and_files()  # Perform cleanup

schedule_cleanup()  # Start the periodic cleanup
