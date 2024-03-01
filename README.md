# YouTube Data Harvesting and Warehousing 📊🚀

## Introduction

Welcome to the YouTube Data Harvesting and Warehousing project – an interactive solution for extracting and analyzing insights from YouTube. This project, developed by a sole contributor, utilizes MongoDB and MySQL for data warehousing, offering a user-friendly interface for dynamic data collection and exploration.

## Workflow

1. **Configure Project:**
    - Clone this repository to your local machine.
    - Install required dependencies by running `pip install -r requirements.txt`.

2. **Set Up Databases:**
    - Create a MySQL database named `youtube_data` manually before running the application. You can use the following SQL query:
      ```sql
      CREATE DATABASE youtube_data;
      ```
    - Ensure you have a MongoDB instance running. No manual database creation is required for MongoDB; the code will create the necessary collections.

3. **User Input:**
    - Run the Streamlit app using `streamlit run app.py`.
    - Enter the total count of YouTube channels you want to analyze.
    - For each channel, a textbox will open. Enter the channel ID for each textbox.

4. **Enable Fetch Details Button:**
    - Once all channel IDs are entered, a "Fetch Details" button will be enabled.

5. **Fetch Details:**
    - Click the "Fetch Details" button to initiate data retrieval.
    - Data will be pulled from the YouTube API and stored in MongoDB.
    - Simultaneously, the data will be pushed to MySQL for structured storage.

6. **View Channel Statistics:**
    - After fetching, select a channel from the dropdown menu.
    - View detailed statistics for the selected channel, including viewership trends, engagement metrics, etc.

7. **Ask Questions About the Channel:**
    - In the dropdown menu, select from a list of predefined questions related to the channel.
    - The app will display answers and insights corresponding to the selected question.

## Key Features

- **Data Harvesting:** Utilize YouTube API to fetch comprehensive data for specified channels.
  
- **Dual Warehousing:** Store data in MongoDB for flexibility and in MySQL for structured, relational storage.

- **Interactive Interface:** User-friendly Streamlit dashboard for seamless data input, retrieval, and analysis.

- **Channel Comparison:** Compare multiple channels to identify patterns and top-performing channels.

- **User-Driven Analytics:** Empower users to explore specific channel statistics and ask targeted questions.

## Getting Started

1. **Clone Repository:**
    ```bash
    git clone https://github.com/your-username/your-repo.git
    ```

2. **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Run Streamlit App:**
    ```bash
    streamlit run app.py
    ```

## Contributing

As the sole contributor to this project, your insights and suggestions are invaluable. Feel free to modify and tailor the code to meet your evolving requirements.

Unlock the full potential of YouTube data analysis with this individually developed solution. Explore the README for installation instructions, usage guidelines, and embark on a journey to transform YouTube data into actionable insights!
