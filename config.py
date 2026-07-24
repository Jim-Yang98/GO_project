import os

# 基本路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "ToS_data")

TARGET_GAMES = {
    "PokemonGO": {
        "ptt": {"board": "PokemonGO", "start_index": 961, "pages": 28},
        "dcard": {"mode": "topic", # 需事先確定好網址結構
                "query": "PokemonGo",
                "pages": 11,
                "comment_limit": 5},
        "baha": {"board_id": 29659, 
                "start_board_page": 10, 
                "end_board_page": 36, 
                "reply_pages": 2}
    },
    # "tower_of_saviors": {
    #     "ptt": {"board": "ToS", "start_index": 4666, "pages": 21},
    #     "dcard": {"mode": "forum", # 需事先確定好網址結構
    #             "query": "tower_of_saviors", 
    #             "pages": 11, 
    #             "comment_limit": 5
    #             },
    #     "baha": {"board_id": 23805, 
    #             "start_board_page": 70, 
    #             "end_board_page": 222, 
    #             "reply_pages": 2}
    # }
}