"""Module for audio utils."""

import os

import azure.cognitiveservices.speech as speechsdk
from const import AZURE_HD_VOICES, LOGGER
from utils.identity import get_speech_token


# TODO leverage streaming to speed up generation
# https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency?pivots=programming-language-csharp#streaming
def text_to_speech(ssml) -> bytes:
    """Use Azure Speech Service and convert SSML to audio bytes."""

    try:
        if os.getenv("AZURE_SPEECH_KEY"):
            LOGGER.info("Using Azure Speech Key authentication")
            speech_config = speechsdk.SpeechConfig(
                subscription=os.environ["AZURE_SPEECH_KEY"],
                region=os.environ["AZURE_SPEECH_REGION"],
            )
        else:
            LOGGER.info("Using Azure Speech Resource ID authentication")
            resource_id = os.environ["AZURE_SPEECH_RESOURCE_ID"]
            region = os.environ["AZURE_SPEECH_REGION"]
            custom_endpoint = os.environ.get("AZURE_SPEECH_CUSTOM_ENDPOINT")
            
            LOGGER.info(f"Speech resource ID: {resource_id}")
            LOGGER.info(f"Speech region: {region}")
            if custom_endpoint:
                LOGGER.info(f"Speech custom endpoint: {custom_endpoint}")
            else:
                LOGGER.info("No custom endpoint specified")
            
            try:
                auth_token = get_speech_token(resource_id, custom_endpoint)
                speech_config = speechsdk.SpeechConfig(
                    auth_token=auth_token,
                    region=region,
                )
            except ValueError as e:
                LOGGER.error(f"Invalid speech resource configuration: {str(e)}")
                raise Exception(f"Speech service configuration error: {str(e)}")
            except Exception as e:
                LOGGER.error(f"Failed to authenticate with speech service: {str(e)}")
                raise Exception(f"Speech service authentication failed: {str(e)}")

        audio_config = None  # enable in-memory audio stream

        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm
        )

        # Creates a speech synthesizer using the Azure Speech Service.
        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=audio_config
        )
        
    except KeyError as e:
        LOGGER.error(f"Missing required environment variable: {str(e)}")
        raise Exception(f"Configuration error: Missing environment variable {str(e)}")
    except Exception as e:
        LOGGER.error(f"Failed to configure speech service: {str(e)}")
        raise

    # Synthesizes the received text to speech.
    result = speech_synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return result.audio_data

    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        LOGGER.warning(f"Speech synthesis canceled: {cancellation_details.reason}")

        if (
            cancellation_details.reason == speechsdk.CancellationReason.Error
            and cancellation_details.error_details
        ):
            LOGGER.error(f"Error details: {cancellation_details.error_details}")

        raise Exception(f"Error details: {cancellation_details.error_details}")

    raise Exception(f"Unknown exit reason: {result.reason}")


def podcast_script_to_ssml(podcast) -> str:
    """Convert podcast script to SSML."""

    podcast_script = podcast["script"]
    ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>"

    for line in podcast_script:
        # Escape SSML special characters
        message = (
            line["message"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        ssml += f"<voice name='{AZURE_HD_VOICES[line['name']]}'>{message}</voice>"

    ssml += "</speak>"

    return ssml
