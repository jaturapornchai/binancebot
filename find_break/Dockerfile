# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# List files in /app directory for debugging
RUN ls -la /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variable
ENV NAME FindBreak

# Run find_break.py when the container launches
CMD ["python", "find_break.py"]

# Troubleshooting steps:
# 1. Ensure find_break.py is in the same directory as the Dockerfile
# 2. Check if the file name is correct (case-sensitive)
# 3. Verify that you're in the correct directory when building the image
# 4. Build the Docker image: docker build -t find-break-app .
# 5. Run the container: docker run -it --env-file .env find-break-app
# 6. If there are errors, check the logs: docker logs <container_id