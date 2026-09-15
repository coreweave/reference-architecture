import textwrap
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL = "Qwen/Qwen3.8-27B"

CHECKPOINT = Path(__file__).resolve().parent.parent / "fine_tuning" / "outputs" / "qwen" / "3.8-27b-pirate-71"
quant_config = BitsAndBytesConfig(load_in_4bit=True)

base_model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    quantization_config=quant_config,
    device_map="auto",
)

tuned_model = PeftModel.from_pretrained(
    base_model,
    str(CHECKPOINT),
)

merged_model = AutoModelForCausalLM.from_pretrained(
    f"{CHECKPOINT}-merged",
    quantization_config=quant_config,
    device_map="auto",
)


tokenizer = AutoTokenizer.from_pretrained(MODEL)


def generate_reply(messages, model, max_new_tokens=256, temperature=0.1):
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    reply = tokenizer.decode(
        outputs[0][inputs.input_ids.shape[1] :],
        skip_special_tokens=True,
    )
    return reply.strip()


def main():
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "Tell me how to write a while loop in Python.",
        },
    ]
    with tuned_model.disable_adapter():
        base_reply = generate_reply(messages, base_model)
    tuned_reply = generate_reply(messages, tuned_model)
    merged_reply = generate_reply(messages, merged_model)

    print(f"\nBase Reply:\n{textwrap.indent(base_reply, '    ')}")
    print(f"\nTuned Reply:\n{textwrap.indent(tuned_reply, '    ')}")
    print(f"\nMerged Reply:\n{textwrap.indent(merged_reply, '    ')}")


if __name__ == "__main__":
    main()
