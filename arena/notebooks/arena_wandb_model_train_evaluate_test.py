# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "wandb",
#     "transformers",
#     "datasets",
#     "evaluate",
#     "accelerate",
#     "scikit-learn",
#     "torch",
# ]
# ///

import marimo

__generated_with = "0.19.4"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _():
    import marimo as mo
    from arena.remote_execution_helpers import shell

    return mo, shell


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CoreWeave AI Labs: W&B Model Training Demo

    /// admonition | About This Notebook
        type: info

    This notebook is a demo adaptation of [W&B HuggingFace artifacts](https://colab.research.google.com/drive/1WObS8JQnVODKG-gxtWVokCvSkKjIWUjt?usp=sharing#scrollTo=06gXuaF8HTBD) to provide an example of AILabs use with W&B integration.
    ///

    /// details | Pipeline Steps

    1. **Setup** - Install dependencies
    2. **Data Acquisition** - Load and log dataset to W&B
    3. **Tokenization** - Preprocess text data
    4. **Training** - Fine-tune model with W&B tracking
    5. **Evaluation** - Test on held-out data
    6. **Inference** - Run predictions on new text
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 1. Setup & Dependencies

    /// attention | Required Packages

    Installing: `wandb`, `transformers`, `datasets`, `evaluate`, `accelerate`, `scikit-learn`, `torch`
    ///
    """)
    return


@app.cell
def _():
    import os

    import wandb

    return os, wandb


@app.cell
def _():
    project_name = "sentiment-analysis-demo"
    entity = "coreweave1"
    return entity, project_name


@app.cell
def _(os):
    # can be "end", "checkpoint" or "false"
    os.environ["WANDB_LOG_MODEL"] = "checkpoint"
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 2. Data Acquisition

    /// admonition | Dataset
        type: info

    Loading the **dair-ai/emotion** dataset with 6 emotion classes: sadness, joy, love, anger, fear, surprise.

    The dataset is saved locally and logged as a W&B artifact for versioning and reproducibility.
    ///
    """)
    return


@app.cell
def _(entity, project_name, wandb):
    from datasets import load_dataset

    def acquire_data():
        with wandb.init(project=project_name, entity=entity, job_type="data-acquisition"):
            # Using dair-ai/emotion dataset (tweet_eval structure changed)
            ds = load_dataset("dair-ai/emotion")
            ds.save_to_disk("emotion_dataset")
            artifact = wandb.Artifact(name="emotion_dataset_raw", type="hf_dataset")
            artifact.add_dir("emotion_dataset")
            wandb.log_artifact(artifact)
        return ds

    dataset = acquire_data()
    return (dataset,)


@app.cell
def _(dataset):
    # What does the dataset look like?
    print(dataset)
    print("\nSample Record:", dataset["validation"][0])

    # What do the labels mean?
    _idx2label = dict(enumerate(dataset["train"].features["label"].names))
    print(f"\nLabel mapping: {_idx2label}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Tokenization

    /// admonition | Preprocessing
        type: info

    Using **DistilRoBERTa** tokenizer to convert text to token IDs.

    - Texts are truncated to max length
    - Sorted by length for efficient batching
    - Tokenized dataset logged as W&B artifact
    ///
    """)
    return


@app.cell
def _(dataset, entity, project_name, wandb):
    from transformers import AutoTokenizer, DataCollatorWithPadding

    MODEL_NAME = "distilroberta-base"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tokenize_data():
        def preprocess_function(examples):
            return tokenizer(examples["text"], truncation=True)

        def length_function(examples):
            return {"length": [len(example) for example in examples["input_ids"]]}

        with wandb.init(project=project_name, entity=entity, job_type="tokenization"):
            wandb.use_artifact("emotion_dataset_raw:latest")

            ds = dataset.map(preprocess_function, batched=True)
            ds = ds.map(length_function, batched=True)
            ds = ds.sort("length")
            ds.save_to_disk("emotion_tokenized_ds")

            artifact = wandb.Artifact(
                name="emotion_tokenized_ds",
                type="tokenized_hf_dataset",
                metadata={"tokenizer": MODEL_NAME},
            )

            artifact.add_dir("emotion_tokenized_ds")
            wandb.log_artifact(artifact)
        return ds

    tokenized_ds = tokenize_data()
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)
    return MODEL_NAME, data_collator, tokenized_ds, tokenizer


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 4. Model Training

    /// attention | Training Configuration

    Fine-tuning **DistilRoBERTa** for emotion classification:

    | Parameter | Value |
    |-----------|-------|
    | Learning Rate | 2e-5 |
    | Batch Size | 16 |
    | Epochs | 3 |
    | Optimizer | AdamW |
    | Metric | F1 (weighted) |
    ///

    /// admonition | W&B Integration
        type: success

    All training metrics, checkpoints, and the final model are automatically logged to Weights & Biases.
    ///
    """)
    return


@app.cell
def _(MODEL_NAME, data_collator, dataset, entity, project_name, tokenized_ds, wandb):
    import evaluate
    import numpy as np
    from transformers import (
        AutoModelForSequenceClassification,
        Trainer,
        TrainingArguments,
    )

    # Get label mappings
    idx2label = dict(enumerate(dataset["train"].features["label"].names))
    label2idx = {v: k for k, v in idx2label.items()}
    num_labels = len(idx2label)

    # Load metrics
    accuracy = evaluate.load("accuracy")
    f1 = evaluate.load("f1")

    def compute_metrics(eval_pred):
        preds, labels = eval_pred
        preds = np.argmax(preds, axis=1)
        acc = accuracy.compute(predictions=preds, references=labels)
        if acc is None:
            acc = {}
        f1_score = f1.compute(predictions=preds, references=labels, average="weighted")
        if f1_score is None:
            f1_score = {}
        return {"accuracy": acc["accuracy"], "f1": f1_score["f1"]}

    def train_model():
        with wandb.init(project=project_name, entity=entity, job_type="training"):
            wandb.use_artifact("emotion_tokenized_ds:latest")

            # Load pre-trained model with classification head
            m = AutoModelForSequenceClassification.from_pretrained(
                MODEL_NAME,
                num_labels=num_labels,
                id2label=idx2label,
                label2id=label2idx,
            )

            # Training arguments
            args = TrainingArguments(
                output_dir="emotion_model",
                learning_rate=2e-5,
                per_device_train_batch_size=16,
                per_device_eval_batch_size=16,
                num_train_epochs=3,
                weight_decay=0.01,
                eval_strategy="epoch",
                save_strategy="epoch",
                load_best_model_at_end=True,
                metric_for_best_model="f1",
                report_to="wandb",
                logging_steps=50,
            )

            # Initialize Trainer
            t = Trainer(
                model=m,
                args=args,
                train_dataset=tokenized_ds["train"],
                eval_dataset=tokenized_ds["validation"],
                processing_class=None,  # Using data_collator instead
                data_collator=data_collator,
                compute_metrics=compute_metrics,
            )

            # Train the model
            t.train()

            # Save model artifact
            t.save_model("emotion_model_final")
            artifact = wandb.Artifact(
                name="emotion_model",
                type="model",
                metadata={"base_model": MODEL_NAME, "num_labels": num_labels},
            )
            artifact.add_dir("emotion_model_final")
            wandb.log_artifact(artifact)

        return m, t

    model, trainer = train_model()
    return idx2label, label2idx, model, trainer


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 5. Model Evaluation

    /// admonition | Test Set Evaluation
        type: info

    Evaluating the trained model on the held-out test set:

    - **Accuracy** and **F1 score** computed
    - **Confusion matrix** logged to W&B
    - Results tracked for experiment comparison
    ///
    """)
    return


@app.cell
def _(entity, idx2label, project_name, tokenized_ds, trainer, wandb):
    def evaluate_model():
        with wandb.init(project=project_name, entity=entity, job_type="evaluation"):
            wandb.use_artifact("emotion_model:latest")

            # Evaluate on test set
            results = trainer.evaluate(tokenized_ds["test"])
            print("Test Results:")
            for key, value in results.items():
                print(f"  {key}: {value:.4f}")

            # Log test metrics
            wandb.log(
                {
                    "test_accuracy": results["eval_accuracy"],
                    "test_f1": results["eval_f1"],
                    "test_loss": results["eval_loss"],
                }
            )

            # Create a simple classification report
            pred_output = trainer.predict(tokenized_ds["test"])
            pred_classes = pred_output.predictions.argmax(-1)
            true_labels = pred_output.label_ids

            # Log confusion data
            wandb.log(
                {
                    "confusion_matrix": wandb.plot.confusion_matrix(
                        probs=None,
                        y_true=true_labels,
                        preds=pred_classes,
                        class_names=list(idx2label.values()),
                    )
                }
            )

        return results, pred_classes

    test_results, test_preds = evaluate_model()
    return test_preds, test_results


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 6. Inference

    /// admonition | Live Predictions
        type: success

    Test the trained model with sample texts. The `predict_emotion()` function can be used for real-time inference.
    ///
    """)
    return


@app.cell
def _(idx2label, model, tokenizer):
    import torch

    # Get the device the model is on
    device = next(model.parameters()).device

    def predict_emotion(text):
        """Predict emotion for a given text."""
        inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
        # Move inputs to the same device as the model
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_class = probs.argmax().item()
            confidence = probs.max().item()

        return {
            "text": text,
            "predicted_emotion": idx2label[predicted_class],
            "confidence": f"{confidence:.2%}",
            "all_scores": {idx2label[i]: f"{score:.2%}" for i, score in enumerate(probs[0].tolist())},
        }

    # Test with sample texts
    sample_texts = [
        "I'm so happy today, everything is going great!",
        "This makes me really angry, I can't believe it happened.",
        "I'm feeling quite sad and lonely right now.",
        "I love spending time with my family.",
        "I'm worried about what might happen tomorrow.",
        "Wow, I didn't expect that at all!",
    ]

    print("=" * 60)
    print("EMOTION PREDICTIONS")
    print("=" * 60)
    for text in sample_texts:
        pred = predict_emotion(text)
        print(f"\nText: {pred['text']}")
        print(f"Predicted: {pred['predicted_emotion']} ({pred['confidence']})")
    print("=" * 60)

    return predict_emotion, sample_texts


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Summary

    /// admonition | Pipeline Complete :rocket:
        type: success

    This notebook demonstrated a complete ML pipeline with W&B integration:

    | Step | Description | W&B Artifact |
    |------|-------------|--------------|
    | 1. Data | Load emotion dataset | `emotion_dataset_raw` |
    | 2. Tokenize | Preprocess with DistilRoBERTa | `emotion_tokenized_ds` |
    | 3. Train | Fine-tune classifier | `emotion_model` |
    | 4. Evaluate | Test set metrics | Logged metrics |
    | 5. Inference | Live predictions | - |

    All artifacts are versioned and tracked in W&B, enabling full reproducibility.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Scratchpad

    /// details | Scratchpad
        type: info

    Use the cell below for experimentation and quick tests. This cell is independent and won't affect the pipeline.
    ///
    """)
    return


@app.cell
def _():
    # Scratchpad - use for experimentation
    # This cell is independent and won't affect the pipeline

    scratch_notes = """
    Quick experiments go here...
    """
    return


if __name__ == "__main__":
    app.run()
