import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_checkpoint = 'cointegrated/rubert-tiny-toxicity'
tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)
model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
model.to(device)
model.eval()

def text2toxicity(text, aggregate=True):
    
    if isinstance(text, str):
        texts = [text]
        single_input = True
    else:
        texts = text
        single_input = False

    with torch.inference_mode():
        inputs = tokenizer(
            texts,
            return_tensors='pt',
            truncation=True,
            padding=True
        ).to(device)

        logits = model(**inputs).logits
        proba = torch.sigmoid(logits)  # shape: [batch_size, num_labels]

    if aggregate:
        # первый логит = "нет токсичности", последний = "тяжелая токсичность"
        # 1 - p(non_toxic) * (1 - p(hard_toxic))
        agg = 1.0 - proba[:, 0] * (1.0 - proba[:, -1])
        agg = agg.cpu().numpy()
        return agg[0] if single_input else agg

    proba = proba.cpu().numpy()
    return proba[0] if single_input else proba
