import argparse
import json
import os
import requests

import whisper_pyannote_fusion

from proj.speech_to_text.speaker_identification import run_llm_speaker_identification
from rss_process import get_rss_feed, get_rss_feed_data, RSS_URL, RSS_FILENAME
from utils import check_required_dirs

from config import HUGGING_FACE_API_KEY


def download_mp3(url_data, filename_mp3):
    """
    Download the mp3 file from the url
    :param url_data: MP3 podcast url
    :param filename_mp3: Filename of the mp3 file
    :return:
    """
    # Download the mp3 file
    r = requests.get(url_data)
    with open(filename_mp3, 'wb') as f:
        f.write(r.content)


def add_speaker_identification(transcript, speakers_json_filename):
    """
    Add the speaker identification to the transcript
    """
    speakers = transcript['speakers']

    if not os.path.exists(speakers_json_filename):
        # Do the speaker identification using LLM
        speakers_dict = run_llm_speaker_identification(transcript)
        # Save the speakers to the json file
        with open(speakers_json_filename, 'w') as f:
            json.dump(speakers_dict, f)
    else:
        with open(speakers_json_filename, 'r') as f:
            speakers_dict = json.load(f)

    speakers = [speakers_dict.get(speaker, "Unknown Speaker") for speaker in speakers]
    transcript['speakers'] = speakers

    return transcript


def process_episode(episode):
    file_prefix = episode['episode']

    # Download the mp3 file if it does not exist into the podcasts folder
    mp3_filename = os.path.join('podcasts', file_prefix + '.mp3')
    if not os.path.exists(mp3_filename):
        print(f'Downloading {episode["episode"]}...')
        download_mp3(episode['url'], mp3_filename)
    audio_filename = mp3_filename

    # Set up the filename that we will use to save the text from the asr
    whisper_json_filename = os.path.join('asr', file_prefix + '.whisper.json')
    pyannote_json_filename = os.path.join('asr', file_prefix + '.pyannote.json')
    pyannote_whisper_json_filename = os.path.join('asr', file_prefix + '.pyannote_whisper.json')
    whisperx_alignment_json_filename = os.path.join('asr', file_prefix + '.whisperx.json')
    output_json_file = os.path.join('transcripts', file_prefix + '.output.json')
    corrected_json_file = os.path.join('transcripts', file_prefix + '.corrected.json')
    markdown_ouput = os.path.join('markdown', file_prefix + '.md')
    speakers_json_filename = os.path.join('asr', file_prefix + '.speakers.json')

    initial_prompt = 'TWIML with Sam Charrington. ' + episode['title'] + ' ' + episode['description']

    try:
        whisper_pyannote_fusion.whisper_pyannote_fusion(audio_filename, 'correct_pyannote_with_whisper',
                                                        whisper_json_file=whisper_json_filename,
                                                        pyannote_json_file=pyannote_json_filename,
                                                        pyannote_whisper_json_filename=pyannote_whisper_json_filename,
                                                        whisperx_alignment_json_filename=whisperx_alignment_json_filename,
                                                        output_json_file=output_json_file,
                                                        corrected_json_file=corrected_json_file,
                                                        initial_prompt=initial_prompt,
                                                        HUGGING_FACE_API_KEY=HUGGING_FACE_API_KEY)
        with open(corrected_json_file, 'r') as f:
            corrected_json = json.load(f)
        corrected_json['title'] = episode['title']
        corrected_json['description'] = episode['description']
        corrected_json['link'] = episode['url']
        corrected_json = add_speaker_identification(corrected_json, speakers_json_filename)
        whisper_pyannote_fusion.transcript_to_workdown(corrected_json, markdown_ouput)
    except Exception as e:
        print(f'Error processing episode {episode["episode"]}: {e}. Skipping ...')

    output2_json_file = os.path.join('transcripts', file_prefix + '.output2.json')
    markdown1_output = os.path.join('markdown', file_prefix + '.1.md')

    try:
        whisper_pyannote_fusion.whisper_pyannote_fusion(audio_filename, 'whisperx_align_pyannote',
                                                        whisper_json_file=whisper_json_filename,
                                                        pyannote_json_file=pyannote_json_filename,
                                                        pyannote_whisper_json_filename=pyannote_whisper_json_filename,
                                                        whisperx_alignment_json_filename=whisperx_alignment_json_filename,
                                                        output_json_file=output2_json_file,
                                                        initial_prompt=initial_prompt,
                                                        HUGGING_FACE_API_KEY=HUGGING_FACE_API_KEY)
        with open(output2_json_file, 'r') as f:
            corrected_json = json.load(f)
        corrected_json['title'] = episode['title']
        corrected_json['description'] = episode['description']
        corrected_json['link'] = episode['url']
        corrected_json = add_speaker_identification(corrected_json, speakers_json_filename)
        whisper_pyannote_fusion.transcript_to_workdown(corrected_json, markdown1_output)
    except Exception as e:
        print(f'Error processing whisperx episode {episode["episode"]}: {e}. Skipping ...')


def run_pipeline(start, end=None):
    """
    Run the pipeline of getting the RSS feed and converting all the podcasts to text
    """

    # Prerequisites
    # Check the folders exist
    check_required_dirs()

    # Download the RSS feed if the file does not exist, or if we have -1 as the start
    if not os.path.exists(RSS_FILENAME) or start == -1:
        get_rss_feed(RSS_URL, RSS_FILENAME)

    # Get the podcast data as a list of dictionaries
    podcast_data = get_rss_feed_data(RSS_FILENAME)

    # If start is -1, process all the episodes
    if start == -1:
        for episode in podcast_data:
            process_episode(episode)
    else:
        # If end is not specified, process only the episode specified in start
        if end is None:
            process_episode(podcast_data[str(start)])
        else:
            # Process all the episodes from start to end
            for episode in range(start, end + 1):
                # Check if the key is in the dictionary
                if str(episode) in podcast_data:
                    process_episode(podcast_data[str(episode)])
                else:
                    print(f'Episode {episode} not found. Skipping...')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Speech to Text Pipeline.")

    parser.add_argument("--start", type=int, required=True, help="Start of the range")
    parser.add_argument("--end", type=int, required=False, help="End of the range")

    args = parser.parse_args()

    run_pipeline(args.start, args.end)