from app.agent.llm import get_llm

if __name__ == "__main__":
    llm = get_llm()
    response = llm.invoke("Привет! Расскажи кратко о Санкт-Петербурге.")
    print(response.content)