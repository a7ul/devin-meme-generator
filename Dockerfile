# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Copy the fonts directory into the container
COPY ./fonts /usr/src/app/fonts

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for testing purposes
RUN apt-get update && apt-get install -y curl

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# Set environment variable to ensure Python output is sent straight to terminal without being buffered
ENV PYTHONUNBUFFERED=1

# Run app.py when the container launches
CMD ["flask", "run"]
