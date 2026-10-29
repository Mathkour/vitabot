def chunck_text(text:str,chunck_size:int=800,overlap:int=100)->list[str]:

    chuncks=[]
    start=0
    text_length=len(text)

    while start < text_length:
        end=start + chunck_size
        chunck=text[start:end]
        chuncks.append(chunck.strip())

        start = end - overlap 

    return [c for c in chuncks if c]