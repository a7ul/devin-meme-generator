# Meme Generator Backend API

This README provides instructions on how to use the Meme Generator Backend API to upload an image and retrieve a meme with overlaid text.

## Setup Instructions

To run this project locally, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/MemeGenBackend.git
   cd MemeGenBackend
   ```

2. Set up a virtual environment (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Docker following the instructions for your operating system:
   - [Windows](https://docs.docker.com/docker-for-windows/install/)
   - [Mac](https://docs.docker.com/docker-for-mac/install/)
   - [Linux](https://docs.docker.com/engine/install/ubuntu/)

5. Set up the Ollama service using Docker:
   ```bash
   docker-compose -f /etc/docker/compose/ollama/docker-compose.yml up -d
   ```

6. Run the Flask application:
   ```bash
   export FLASK_APP=app.py
   export FLASK_ENV=development
   flask run
   ```

7. The application will be available at `http://localhost:5000`.

## Endpoints

### Upload Image

- **Endpoint**: `/upload`
- **Method**: POST
- **Description**: Upload an image to generate a meme.
- **Form Data**:
  - `file`: The image file to upload.
- **Curl Example**:
  ```bash
  curl -X POST -F 'file=@path_to_your_image.jpg' https://meme-generator-backend-r6fonj7p.devinapps.com/upload
  ```

### Get Meme Generation Status

- **Endpoint**: `/status/<job_id>`
- **Method**: GET
- **Description**: Get the status of the meme generation job.
- **URL Parameters**:
  - `job_id`: The unique identifier for the meme generation job.
- **Authentication**: Basic Auth (username: admin, password: password)
- **Curl Example**:
  ```bash
  curl -u admin:password https://meme-generator-backend-r6fonj7p.devinapps.com/status/your_job_id
  ```

### Retrieve Generated Meme

- **Endpoint**: `/result/<job_id>`
- **Method**: GET
- **Description**: Retrieve the generated meme image.
- **URL Parameters**:
  - `job_id`: The unique identifier for the meme generation job.
- **Authentication**: Basic Auth (username: admin, password: password)
- **Curl Example**:
  ```bash
  curl -u admin:password https://meme-generator-backend-r6fonj7p.devinapps.com/result/your_job_id
  ```

## Usage Flow

1. Use the `/upload` endpoint to upload your image. You will receive a JSON response with a `job_id`.
2. Use the `/status/<job_id>` endpoint to check the status of your meme generation job.
3. Once the status is 'completed', use the `/result/<job_id>` endpoint to retrieve the generated meme image.

## Notes

- The `/status/<job_id>` endpoint will return a 404 error if the job ID is not found.
- The `/result/<job_id>` endpoint will serve the generated meme image file directly.
- The meme text is automatically generated based on the content of the image and is designed to be humorous and brief, fitting within one or two lines.
- The generated meme images are stored under their respective job IDs in a separate folder for organized retrieval at any time.
- The generated meme image will be available for 1 hour after completion before being automatically deleted by the cleanup mechanism.

For any issues or further assistance, please contact the backend support team.
