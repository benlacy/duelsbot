FEER_GUILD_ID = 491059327038259231

def get_rank(mmr: int) -> str:
    if mmr >= 1500: return "Rank S"
    elif mmr >= 1340: return "Rank X"
    elif mmr >= 1175: return "Rank A"
    elif mmr >= 986: return "Rank B"
    elif mmr >= 815: return "Rank C"
    else: return "Rank D"


