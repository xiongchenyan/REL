from http.server import BaseHTTPRequestHandler
import torch
import time
import json

from REL.mention_detection import MentionDetection
from REL.utils import process_results
from flair.models import SequenceTagger

API_DOC = "API_DOC"


"""
Class/function combination that is used to setup an API that can be used for e.g. GERBIL evaluation.
"""

def make_handler(
    base_url, wiki_subfolder, model, tagger_ner
):
    class GetHandler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.model = model
            self.tagger_ner = tagger_ner

            self.base_url = base_url
            self.wiki_subfolder = wiki_subfolder

            self.custom_ner = not isinstance(tagger_ner, SequenceTagger)
            self.mention_detection = MentionDetection(base_url, wiki_subfolder)

            super().__init__(*args, **kwargs)

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                bytes(
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "label": "status",
                            "message": "up",
                            "color": "green",
                        }
                    ),
                    "utf-8",
                )
            )
            return

        def do_POST(self):
            """
            Returns response.

            :return:
            """
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            self.send_response(200)
            self.end_headers()

            text, spans = self.read_json(post_data)
            response = self.generate_response(text, spans)

            # print('response in server.py code:\n\n {}'.format(response))
            self.wfile.write(bytes(json.dumps(response), "utf-8"))
            return

        def read_json(self, post_data):
            """
            Reads input JSON message.

            :return: document text and spans.
            """

            data = json.loads(post_data.decode("utf-8"))
            text = data["text"]
            text = text.replace("&amp;", "&")

            # GERBIL sends dictionary, users send list of lists.
            try:
                spans = [list(d.values()) for d in data["spans"]]
            except Exception:
                spans = data["spans"]
                pass

            return text, spans

        def generate_response(self, text, spans):
            """
            Generates response for API. Can be either ED only or EL, meaning end-to-end.

            :return: list of tuples for each entity found.
            """

            if len(text) == 0:
                return []

            if len(spans) > 0:
                # Now we do ED.
                processed = {API_DOC: [text, spans]}
                mentions_dataset, total_ment = self.mention_detection.format_spans(
                    processed
                )
            elif self.custom_ner:
                # Verify if we have spans.
                if len(spans) == 0:
                    print("No spans found for custom MD.")
                    return []
                spans = self.tagger_ner(text)

                processed = {API_DOC: [text, spans]}
                mentions_dataset, total_ment = self.mention_detection.format_spans(
                    processed
                )
            else:
                # EL
                processed = {API_DOC: [text, spans]}
                mentions_dataset, total_ment = self.mention_detection.find_mentions(
                    processed, self.tagger_ner
                )

            # Disambiguation
            predictions, timing = self.model.predict(mentions_dataset)

            # Process result.
            result = process_results(
                mentions_dataset,
                predictions,
                processed,
                include_offset=False if ((len(spans) > 0) or self.custom_ner) else True,
            )

            # Singular document.
            if len(result) > 0:
                return [*result.values()][0]

            return []

    return GetHandler
