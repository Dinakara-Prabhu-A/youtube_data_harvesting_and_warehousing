import streamlit as st
from googleapiclient.discovery import build
from sqlalchemy import create_engine, Column, String, Integer, Text, LargeBinary, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from numerize import numerize
import pymysql
import pymongo
import aiohttp
import seaborn as sns 
import asyncio
import time
import pandas as pd
from datetime import datetime
from isodate import parse_duration



class YouTubeAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def get_channel_info(self, channel_ids):
        channel_info = []
        playlist_ids = []

        request = self.youtube.channels().list(
            part="snippet,contentDetails,statistics,topicDetails,status",
            id=",".join(channel_ids)
        )

        response = request.execute()
        for i in range(len(response['items'])):
            data = dict(
                channel_id=response['items'][i]['id'],
                channel_name=response['items'][i]["snippet"]["title"],
                channel_type=response['items'][i]["topicDetails"]["topicCategories"],
                channel_views=response['items'][i]["statistics"]["viewCount"],
                channel_description=response['items'][i]["snippet"]["description"],
                channel_status=response['items'][i]["status"]["privacyStatus"],
                subscription_count=response['items'][i]["statistics"]["subscriberCount"],
                total_videos = response['items'][i]["statistics"]["videoCount"],
                playlist_id=response['items'][i]["contentDetails"]["relatedPlaylists"]["uploads"]
            )
            channel_info.append(data)
            playlist_ids.append(data['playlist_id'])

        return channel_info, playlist_ids

    def get_video_ids(self, playlist_ids):
        video_ids = []
        playlist = []
        for playlist_id in playlist_ids:
            next_page_token = None
            more_pages = True
            while more_pages:
                request = self.youtube.playlistItems().list(
                    part='snippet', maxResults=50, pageToken=next_page_token, playlistId=playlist_id
                )
                response = request.execute()
                for i in range(len(response['items'])):
                    data = dict(
                        playlist_id=response['items'][i]['snippet']["playlistId"],
                        playlist_items_id=response['items'][i]['id'],
                        channel_id=response['items'][i]['snippet']["channelId"],
                        playlist_name=response['items'][i]["snippet"]["title"]
                    )
                    playlist.append(data)
                    video_ids.append(response['items'][i]['snippet']['resourceId']['videoId'])
                next_page_token = response.get("nextPageToken")
                more_pages = next_page_token is not None

        return video_ids, playlist

    async def get_video_details_async(self, session, video_ids):
        video_details = []
        for i in range(0, len(video_ids), 50):
            request = self.youtube.videos().list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(video_ids[i:i + 50]),
            )

            async with session.get(request.uri) as response:
                data = await response.json()

                for video in data['items']:
                    details = dict(
                        video_id=video["id"],
                        channel_id=video['snippet']["channelId"],
                        video_name=video["snippet"]["title"],
                        video_description=video["snippet"]["description"],
                        published_date=video["snippet"]["publishedAt"],
                        view_count=video["statistics"]["viewCount"],
                        like_count=video["statistics"].get("likeCount", 0),
                        dislike_count=video["statistics"].get("dislikeCount", 0),
                        favorite_count=video["statistics"].get("favoriteCount", ""),
                        comment_count=video["statistics"].get("commentCount"),
                        duration=video["contentDetails"]["duration"],
                        caption_status=video["contentDetails"].get("caption", "")
                    )
                    video_details.append(details)

        return video_details

    async def get_comment_async(self, session, video_id):
        comment = []
        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100
            )

            request_url = request.uri
            async with session.get(request_url) as response:
                data = await response.json()

                for i in data['items']:
                    comment_data = dict(
                        comment_id=i.get("id"),
                        video_id=video_id,
                        comment_text=i["snippet"]["topLevelComment"]["snippet"].get("textDisplay"),
                        comment_author=i["snippet"]["topLevelComment"]["snippet"].get("authorDisplayName"),
                        comment_published_date=i["snippet"]["topLevelComment"]["snippet"].get("publishedAt")
                    )
                    comment.append(comment_data)

        except Exception as e:
            print(f"Error fetching comments for video {video_id}: {e}")

        return comment

    async def main(self, video_ids):
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.get_video_details_async(session, video_ids[i:i + 50])
                for i in range(0, len(video_ids), 50)
            ]
            results = await asyncio.gather(*tasks)

        all_video_details = [details for sublist in results for details in sublist]
        print(f"Total video details: {len(all_video_details)}")
        return all_video_details

    async def main_comments(self, video_ids):
        async with aiohttp.ClientSession() as session:
            tasks = [self.get_comment_async(session, video_id) for video_id in video_ids]
            comments = await asyncio.gather(*tasks)

        all_comments = [comment for sublist in comments for comment in sublist]
        print(f"Total comments: {len(all_comments)}")
        return all_comments

class MongoDBHandler:
    def __init__(self,mongo_uri):
        self.mongo_uri = mongo_uri
        self.client = pymongo.MongoClient(mongo_uri)
        self.db = self.client["Youtube_data_harvesting"]

    def push_data_to_mongodb(self, channel_info, video_details, comment, playlist):
        channel_collection = self.db['channel']
        video_collection = self.db['video']
        comment_collection = self.db['comment']
        playlist_collection = self.db['playlist']

        channel_collection.insert_many(channel_info)
        video_collection.insert_many(video_details)
        comment_collection.insert_many(comment)
        playlist_collection.insert_many(playlist)

    def remove_duplicates(self, collection_name, field_name):
        pipeline = [
            {
                '$group': {
                    '_id': {field_name: f'${field_name}'},
                    'uniqueIds': {'$addToSet': '$_id'},
                    'count': {'$sum': 1}
                }
            },
            {
                '$match': {
                    'count': {'$gt': 1}
                }
            }
        ]

        cursor = self.db[collection_name].aggregate(pipeline)

        for doc in cursor:
            doc['uniqueIds'].pop(0)  # Keep the first occurrence and remove the others
            self.db[collection_name].delete_many({'_id': {'$in': doc['uniqueIds']}})

    def data_cleaning(self):
        self.remove_duplicates('channel', 'channel_id')
        self.remove_duplicates('video', 'video_id')
        self.remove_duplicates('playlist', 'playlist_items_id')
        self.remove_duplicates('comment', 'comment_id')

class MySQLHandler:
    def __init__(self, connection_string):
        self.engine = create_engine(connection_string)
        self.Base = declarative_base()
        self.create_tables()
        
    def create_tables(self):
        class Channel(self.Base):
            __tablename__ = 'channel'
            channel_id = Column(String(255), primary_key=True)
            channel_name = Column(String(255))
            channel_type = Column(String(255))  # Store as a comma-separated string
            channel_views = Column(Integer)
            channel_description = Column(Text)  # Use Text for longer descriptions
            channel_status = Column(String(255))
            subscription_count = Column(Integer)
            total_videos = Column(Integer)
            playlist_id = Column(String(255))
            
        class Video(self.Base):
            __tablename__ = 'video'
            video_id = Column(String(255), primary_key=True)
            channel_id = Column(String(255))  # Foreign key relationship
            video_name = Column(String(255))
            video_description = Column(Text)
            published_date = Column(DateTime)
            view_count = Column(Integer)
            like_count = Column(Integer)
            dislike_count = Column(Integer)
            favorite_count = Column(Integer)
            comment_count = Column(Integer)
            duration = Column(String(20))  # Store as string due to variable format
            caption_status = Column(Boolean)
            
        class Comment(self.Base):
            __tablename__ = 'comment'
            comment_id = Column(String(255), primary_key=True)
            video_id = Column(String(255))
            comment_text = Column(Text)
            comment_author = Column(String(255))
            comment_published_date = Column(DateTime)
            
        class Playlist(self.Base):
            __tablename__ = 'playlist'
            playlist_id = Column(String(255))
            playlist_items_id = Column(String(255), primary_key=True)
            channel_id = Column(String(255))  # Foreign key to channels
            playlist_name = Column(String(255))

        self.Base.metadata.create_all(self.engine)
        
    def create_dataframe(self,db):
        channel_df = pd.DataFrame(list(db.channel.find({},{'_id':0})))  
        video_df = pd.DataFrame(list(db.video.find({},{'_id':0})))
        comment_df = pd.DataFrame(list(db.comment.find({},{'_id':0})))
        playlist_df = pd.DataFrame(list(db.playlist.find({},{'_id':0})))
        channel_df['channel_type'] = channel_df['channel_type'].apply(lambda x: ', '.join(map(str, x)))
        video_df['like_count'] = video_df['like_count'].astype(int) 
        video_df['view_count'] = video_df['view_count'].astype(int) 
        

        return channel_df,video_df,comment_df,playlist_df

    def push_to_mysql(self, channel_df, video_df, comment_df, playlist_df):
        channel_df.to_sql('channel', self.engine, if_exists='replace', index=False, index_label='channel_id')
        video_df.to_sql('video', self.engine, if_exists='replace', index=False, index_label='video_id')
        comment_df.to_sql('comment', self.engine, if_exists='replace', index=False, index_label='comment_id')
        playlist_df.to_sql('playlist', self.engine, if_exists='replace', index=False, index_label='playlist_items_id')

class YouTubeDataHandler:
    def __init__(self, api_key, mongo_uri, mysql_uri):
        self.api_key = api_key
        self.youtube_api = YouTubeAPI(api_key)
        self.mongo_handler = MongoDBHandler(mongo_uri)
        self.mysql_handler = MySQLHandler(mysql_uri)

    def process_data(self, channel_ids):
        # YouTube API
        with st.spinner("***Fetching Channel Details...***"):
            channel_info, playlist_ids = self.youtube_api.get_channel_info(channel_ids)
        with st.spinner("***Fetching Vedio Details...***"):
            video_ids, playlist = self.youtube_api.get_video_ids(playlist_ids)
            video_details = asyncio.run(self.youtube_api.main(video_ids))
        with st.spinner("***Fetching Comments Details...***"):
            comment = asyncio.run(self.youtube_api.main_comments(video_ids))
        
        with st.spinner("***Loading.....***"):
            # MongoDB
            self.mongo_handler.push_data_to_mongodb(channel_info, video_details, comment, playlist)
            self.mongo_handler.data_cleaning()

            # MySQL
            db = self.mongo_handler.db
            channel_df, video_df, comment_df, playlist_df = self.mysql_handler.create_dataframe(db)
            self.mysql_handler.push_to_mysql(channel_df, video_df, comment_df, playlist_df)
        st.success("Youtube Data Fetched Successfully :thumbsup:")
    def show_sql_data(self,channel_ids):
        engine = self.mysql_handler.engine
        channel_names = []
        if all(channel_ids):
            if len(channel_ids) == 1:
                channel_names = pd.read_sql_query(f"""select channel_name from channel where channel_id = "{channel_ids[0]}";""",engine)['channel_name'].tolist()
            else:
                channel_names = pd.read_sql_query(f"select channel_name from channel where channel_id in {tuple(channel_ids)}",engine)['channel_name'].tolist()        
        select_channel_name_box = st.selectbox("Select the channel name",channel_names)
        try:
            channel_df = pd.read_sql_query(f"""select * from channel where channel_name = "{select_channel_name_box}";""",engine)
            video_df = pd.read_sql_query(f"""select * from video where channel_id = "{channel_df['channel_id'].iloc[0]}";""",engine)
            comment_df = pd.read_sql_query(f'''select * from comment where video_id in {tuple(video_df['video_id'])}''', engine)
            st.divider()
            return video_df,comment_df,channel_df
        except IndexError or UnboundLocalError:
            pass

    def streamlit_chart_view (self,video_df,comment_df,channel_df):
            subscriber = numerize.numerize(int(channel_df['subscription_count'].iloc[0]),1)
            Total_views = numerize.numerize(int(channel_df['channel_views'].iloc[0]),1)
            Total_videos = numerize.numerize(int(channel_df['total_videos'].iloc[0]),1)
            st.markdown(f"""
                        <link rel="preconnect" href="https://fonts.googleapis.com">
                        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                        <link href="https://fonts.googleapis.com/css2?family=Protest+Strike&family=Teko&family=Tilt+Prism&display=swap" rel="stylesheet">
                        <div class = channel-container > <h1 style ="font-size:60px; margin-top:30px; margin-inline:70px;
                        margin-right :10px;margin-left :10px;font-family: 'Tilt Prism', sans-serif;color: rgb(2, 251, 180)">Channel Details</h1>
                            <div class = Channel-Stats> 
                                <h4>Total views</h4> 
                                <h2>{Total_views}</h2>
                            </div>
                            <div class = Channel-Stats> 
                                <h4>Total Vedios</h4> 
                                <h2>{channel_df['total_videos'].iloc[0]}</h2>
                            </div>
                            <div class = Channel-Stats> 
                                <h4>Subscribers</h4> 
                                <h2>{subscriber}</h2>
                            </div>
                        </div>
                        <style>
                        .channel-container{{ 
                        height:200px; width :100; display: flex; justify-content: flex-start;border: 1px solid rgb(2, 251, 180);padding: 0;border-radius:10px;box-shadow: 0 0 10px rgb(2, 251, 180);}}
                        .Channel-Stats {{height:140px; margin-right: 20px;width :180px;text-align: center;border: 3px solid rgb(2, 251, 180);padding: 0;border-radius:10px;box-shadow: 0 0 10px rgb(0, 226, 254);
                                        margin-top :30px;}}
                        .Channel-Stats h2{{margin:0;padding:0;font-family: 'Teko', sans-serif;,margin-top:10px;letter-spacing:1.5px ;  }}
                        .Channel-Stats h4{{font-family: 'Teko', sans-serif;font-size: 30px;letter-spacing:1px;}}
                        </style>  
                            """,unsafe_allow_html=True)
            video_df['published_date'] = video_df['published_date'].apply(lambda x: datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d"))
            video_df['view_count'] = pd.to_numeric(video_df['view_count'])
            video_df['like_count'] = pd.to_numeric(video_df['like_count'])
            video_df['comment_count'] = pd.to_numeric(video_df['comment_count'])
            video_df['dislike_count'] = pd.to_numeric(video_df['dislike_count'])
            video_df['month'] = pd.to_datetime(video_df['published_date']).dt.strftime('%b')
            video_per_month_df = video_df.groupby('month',as_index = False).size()
            for i in range(3):
                st.markdown('##') 
            sort_month_order = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
            video_per_month_df.index= pd.CategoricalIndex(video_per_month_df['month'],sort_month_order,ordered=True)
            video_per_month_df.rename(columns={'month': 'Months','size':'Number of videos'}, inplace=True)
            video_per_month_df = video_per_month_df.sort_index()
            
            left_column,middle_column,right_column = st.columns(3)
            with left_column:
                st.markdown("""<style>.st-emotion-cache-zjxchj{height: 600px; width :100; border : 1px solid red;}</style>""",unsafe_allow_html=True)
                st.markdown("""<h3 style="text-align: left;margin-inline:30px;letter-spacing:1px; 
                            font-family: 'Teko', sans-serif; color :rgb(255, 112, 218 )">Videos uploaded in Months</h3>""", unsafe_allow_html=True)
                st.bar_chart(video_per_month_df,x='Months',y='Number of videos',height = 350,width=525)
            st.markdown("""<style> .st-emotion-cache-1r6slb0{
                        border: 1px solid rgb(2, 251, 180);padding:0;width :300px;border-radius :20px;
                        box-shadow: 0 0 10px rgb(2, 251, 180);}    </style>""", unsafe_allow_html=True)
            with right_column:
                df_sorted = video_df.sort_values(by='view_count', ascending=False)
                top_10_view_count = df_sorted.head(10)
                top_10_view_count.rename(columns = {'video_name': 'Title', 'view_count': 'Views'},inplace=True) 
                
                st.markdown("""<h3 style="text-align: left;margin-inline:30px;letter-spacing:1px;margin-top:20px; 
                            font-family: 'Teko', sans-serif; color :rgb(255, 112, 218 )">Top 10 Most-Watched Videos</h3>""", unsafe_allow_html=True)
                st.bar_chart(top_10_view_count,x='Title',y='Views',height = 350,width=525)
            
            with middle_column:
                df_sorted = video_df.sort_values(by='like_count', ascending=False)
                top_10_like_count = df_sorted.head(10)
                top_10_like_count.rename(columns = {'video_name': 'Title', 'like_count': 'Likes'},inplace=True) 
                st.markdown("""<h3 style="text-align: left;margin-inline:30px;letter-spacing:1px;margin-top:20px; 
                            font-family: 'Teko', sans-serif; color :rgb(255, 112, 218 )">Top 10 Most-liked Videos</h3>""", unsafe_allow_html=True)
                st.bar_chart(top_10_like_count,x='Title',y='Likes',height = 350,width=525)

    def sql_query_time(self,channel_ids):
        
        engine = self.mysql_handler.engine   
        
        l=[ 'What are the names of all the videos and their corresponding channels?',
            'Which channels have the most number of videos, and how many videos do they have?',
            'What are the top 10 most viewed videos and their respective channels?',
            'How many comments were made on each video, and what are their corresponding video names?',
            'Which videos have the highest number of likes, and what are their corresponding channel names?',
            'What is the total number of likes and dislikes for each video, and what are their corresponding video names?',
            'What is the total number of views for each channel, and what are their corresponding channel names?',
            'What are the names of all the channels that have published videos in the year 2022?',
            'What is the average duration of all videos in each channel, and what are their corresponding channel names?',
            'Which videos have the highest number of comments, and what aren their corresponding channel names?']
        select_box = st.selectbox("You can click this to view there answer",l)
        if len(channel_ids)>1:
            if select_box == 'What are the names of all the videos and their corresponding channels?':
                q= pd.read_sql_query(f""" SELECT v.video_name as 'Video Name', c.channel_name as 'Channel Name'
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id IN {tuple(channel_ids)};""",engine)
                st.dataframe(q)
            if select_box == 'Which channels have the most number of videos, and how many videos do they have?':
                q = pd.read_sql_query(f""" SELECT c.channel_name as "Channel Name", COUNT(*) AS "Number Of Videos"
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id IN {tuple(channel_ids)}
                                            GROUP BY c.channel_name
                                            ORDER BY COUNT(*) DESC;""",engine)
                st.dataframe(q)
            if select_box == 'What are the top 10 most viewed videos and their respective channels?':
                
                q = pd.read_sql_query(f'''
                    SELECT v.video_name AS "Video Title", v.view_count as "Views",c.channel_name as "Channel Name" FROM video v JOIN channel c ON v.channel_id = c.channel_id
                    WHERE c.channel_id IN {tuple(channel_ids)}
                    ORDER BY v.view_count DESC LIMIT 10;''',engine)
                st.dataframe(q)
            if select_box == 'How many comments were made on each video, and what are their corresponding video names?':
                q = pd.read_sql_query(f"""SELECT video_name as 'Video Title', comment_count as 'Comment Count' FROM video WHERE channel_id IN {tuple(channel_ids)};""", engine)
                st.dataframe(q)
            if select_box =='Which videos have the highest number of likes, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT v.video_name AS "Video Title", v.like_count AS "likes", c.channel_name AS "Channel Name" 
                        FROM video v 
                        JOIN channel c ON v.channel_id = c.channel_id
                        WHERE c.channel_id IN {tuple(channel_ids)}
                        ORDER BY v.like_count DESC 
                        LIMIT 10;""", engine)
                st.dataframe(q)
            if select_box == 'What is the total number of likes and dislikes for each video, and what are their corresponding video names?':
                q = pd.read_sql_query(f"""SELECT video_name AS "Video Title", like_count as "Likes", dislike_count as "Dislike" FROM video WHERE channel_id IN {tuple(channel_ids)};
                        """, engine)
                st.dataframe(q)
            if select_box == 'What is the total number of views for each channel, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT c.channel_name as 'Channel Name', SUM(v.view_count) AS 'Total Views' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id WHERE c.channel_id in {tuple(channel_ids)}
                                            GROUP BY c.channel_id, c.channel_name;""",engine)
                st.dataframe(q)
            if select_box == 'What are the names of all the channels that have published videos in the year 2022?':
                q = pd.read_sql_query(f"""  SELECT DISTINCT c.channel_name as 'Channel Name' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id
                                            WHERE YEAR(STR_TO_DATE(v.published_date, '%%Y-%%m-%%dT%%H:%%i:%%sZ')) = 2022
                                            AND c.channel_id IN {tuple(channel_ids)};
                                        """, engine)
                st.dataframe(q)
            if select_box == 'What is the average duration of all videos in each channel, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""  SELECT c.channel_name as 'Channel Name',
                                            CONCAT(
                                            SEC_TO_TIME(
                                            CAST(AVG(SUBSTRING_INDEX(SUBSTRING_INDEX(v.duration, 'PT', -1), 'M', 1) * 60 +
                                            SUBSTRING_INDEX(SUBSTRING_INDEX(v.duration, 'M', -1), 'S', 1)) AS SIGNED))
                                            ) AS 'Average Duration Time' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id 
                                            WHERE c.channel_id IN {tuple(channel_ids)}
                                            GROUP BY c.channel_name;
                                            """,engine)
                st.dataframe(q)
            if select_box == 'Which videos have the highest number of comments, and what aren their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT v.video_name as 'Video Title',c.channel_name as 'Channel Name',
                                            v.comment_count as 'Comment Count'
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id IN {tuple(channel_ids)}
                                            ORDER BY v.comment_count DESC
                                            LIMIT 1;""",engine)
                st.dataframe(q)
        if len(channel_ids)==1:
            if select_box == 'What are the names of all the videos and their corresponding channels?':
                q= pd.read_sql_query(f""" SELECT v.video_name as 'Video Name', c.channel_name as 'Channel Name'
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id ='{channel_ids[0]}';""",engine)
                st.dataframe(q)
            if select_box == 'Which channels have the most number of videos, and how many videos do they have?':
                q = pd.read_sql_query(f""" SELECT c.channel_name as "Channel Name", COUNT(*) AS "Number Of Videos"
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id ='{channel_ids[0]}'
                                            GROUP BY c.channel_name
                                            ORDER BY COUNT(*) DESC;""",engine)
                st.dataframe(q)
            if select_box == 'What are the top 10 most viewed videos and their respective channels?':
                
                q = pd.read_sql_query(f'''
                    SELECT v.video_name AS "Video Title", v.view_count as "Views",c.channel_name as "Channel Name" FROM video v JOIN channel c ON v.channel_id = c.channel_id
                    WHERE c.channel_id ='{channel_ids[0]}'
                    ORDER BY v.view_count DESC LIMIT 10;''',engine)
                st.dataframe(q)
            if select_box == 'How many comments were made on each video, and what are their corresponding video names?':
                q = pd.read_sql_query(f"""SELECT video_name as 'Video Title', comment_count as 'Comment Count' FROM video WHERE channel_id ='{channel_ids[0]}';""", engine)
                st.dataframe(q)
            if select_box =='Which videos have the highest number of likes, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT v.video_name AS "Video Title", v.like_count AS "likes", c.channel_name AS "Channel Name" 
                        FROM video v 
                        JOIN channel c ON v.channel_id = c.channel_id
                        WHERE c.channel_id ='{channel_ids[0]}'
                        ORDER BY v.like_count DESC 
                        LIMIT 10;""", engine)
                st.dataframe(q)
            if select_box == 'What is the total number of likes and dislikes for each video, and what are their corresponding video names?':
                q = pd.read_sql_query(f"""SELECT video_name AS "Video Title", like_count as "Likes", dislike_count as "Dislike" FROM video WHERE channel_id ='{channel_ids[0]}';
                        """, engine)
                st.dataframe(q)
            if select_box == 'What is the total number of views for each channel, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT c.channel_name as 'Channel Name', SUM(v.view_count) AS 'Total Views' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id WHERE c.channel_id ='{channel_ids[0]}'
                                            GROUP BY c.channel_id, c.channel_name;""",engine)
                st.dataframe(q)
            if select_box == 'What are the names of all the channels that have published videos in the year 2022?':
                q = pd.read_sql_query(f"""  SELECT DISTINCT c.channel_name as 'Channel Name' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id
                                            WHERE YEAR(STR_TO_DATE(v.published_date, '%%Y-%%m-%%dT%%H:%%i:%%sZ')) = 2022
                                            AND c.channel_id ='{channel_ids[0]}';
                                        """, engine)
                st.dataframe(q)
            if select_box == 'What is the average duration of all videos in each channel, and what are their corresponding channel names?':
                q = pd.read_sql_query(f"""  SELECT c.channel_name as 'Channel Name',
                                            CONCAT(
                                            SEC_TO_TIME(
                                            CAST(AVG(SUBSTRING_INDEX(SUBSTRING_INDEX(v.duration, 'PT', -1), 'M', 1) * 60 +
                                            SUBSTRING_INDEX(SUBSTRING_INDEX(v.duration, 'M', -1), 'S', 1)) AS SIGNED))
                                            ) AS 'Average Duration Time' FROM channel c
                                            JOIN video v ON c.channel_id = v.channel_id 
                                            WHERE c.channel_id ='{channel_ids[0]}'
                                            GROUP BY c.channel_name;
                                            """,engine)
                st.dataframe(q)
            if select_box == 'Which videos have the highest number of comments, and what aren their corresponding channel names?':
                q = pd.read_sql_query(f"""SELECT v.video_name as 'Video Title',c.channel_name as 'Channel Name',
                                            v.comment_count as 'Comment Count'
                                            FROM video v
                                            JOIN channel c ON v.channel_id = c.channel_id
                                            WHERE c.channel_id ='{channel_ids[0]}' 
                                            ORDER BY v.comment_count DESC
                                            LIMIT 1;""",engine)
                st.dataframe(q)
if __name__ == "__main__":
    st.set_page_config(page_title="YouTube Data Analyser",layout="wide",page_icon=":chart_with_upwards_trend:",initial_sidebar_state="expanded")
    st.markdown("""<style>body {background-color: #707B7C;margin: 0; /* Remove default body margin */}
    h1 {color: #ffffff;margin-top: 0; /* Remove top margin for h1 */}div.block-container {padding-top: 1rem;}
    </style><h1>YouTube Data Analyzer</h1>""", unsafe_allow_html=True)
    channel_ids = []
    user_num_input = st.number_input('How many YouTube channel IDs would you like to analyze?',1,10,1)
    st.markdown("""<style> div[class = "stNumberInput"] label p {font-size:20px;color : #ffffff;font-style : italic }div [data-testid="stNumberInputContainer"]{ 
                    width : 120px;height : 40px;margin-left : 30px;}div [data-testid="stNumberInput"]{display :flex;justify-content : flex-start;margin:0;
                    }.stNumberInput{width : 100px;}div[class*="stTextInput"] label p {font-size: 15px;color: white; </style>""", unsafe_allow_html=True)
    col1,col2 = st.columns(2)
    for i in range(1,user_num_input+1):
        columns = col1 if i%2 != 0 else col2
        
        with columns:
            channel_id = st.text_input(f"***Enter the Channel ID {i}***")
            channel_ids.append(channel_id)
            
            
    api_key = "AIzaSyAMrVzei0Af4qSEKcMuTiYgodDVTVQeZtU"
    mongo_uri = 'mongodb://localhost:27017'
    mysql_uri = 'mysql+pymysql://root:Din%401110@localhost:3306/youtube_data'
    youtube_data_handler = YouTubeDataHandler(api_key, mongo_uri, mysql_uri)
    try:
        if all(channel_ids):
            fetch_button = st.button("**Fetch Details**")
            if fetch_button:
                youtube_data_handler.process_data(channel_ids)
                
    except Exception as e:
        pass
    result = youtube_data_handler.show_sql_data(channel_ids)
    if result is not None:
        video_df, comment_df, channel_df = result
    try:
        youtube_data_handler.streamlit_chart_view (video_df,comment_df,channel_df)
        youtube_data_handler.sql_query_time(channel_ids) 
    except NameError as e:
        pass

