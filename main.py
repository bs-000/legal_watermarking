import itertools
import json
import os
import shutil
from os.path import exists

import numpy as np
import pandas as pd
import torch
import langid
from datasets import Dataset
from scipy.stats import ttest_rel
from torchdata.stateful_dataloader import StatefulDataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils.quantization_config import Mxfp4Config

from data.prompts import instruct_exams, system_exams
from markllm.auto_watermark import AutoWatermark
from markllm.transformers_config import TransformersConfig

hf_cache = '' # TODO: add your cache directory
os.environ['HF_HOME'] = hf_cache
hf_token = '' # TODO: add your huggingface token
str_data_path = './data/'
str_results_path = './results/'
str_zjs = 'zjs_faelle'
str_benchathon = 'benchathon'
str_task_id = 'task_id'
str_input_text = 'input_text'
str_input_length = 'input_length'
str_gold_length = 'gold_length'
str_unwatermarked_text = 'unwatermarked_text'
str_unwatermarked_length = 'unwatermarked_length'
str_watermarked_text = '_watermarked_text'
str_watermarked_length = '_watermarked_length'
str_watermarked_score = '_watermarked_score'
watermarks = ['EXP', 'KGW']
data_types = [str_zjs, str_benchathon ]
str_model_name_gemma = 'google/gemma-4-31B-it' # https://huggingface.co/google/gemma-4-31B-it
str_model_name_gptoss = 'openai/gpt-oss-120b' # https://huggingface.co/openai/gpt-oss-120b
str_model_name_llama = 'meta-llama/Llama-3.3-70B-Instruct' # https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct
model_names = [str_model_name_gemma, str_model_name_gptoss, str_model_name_llama]
device = "cuda" if torch.cuda.is_available() else "cpu"
dataloader_batchsize = 2
dataloader_num_workers = 8


def read_complete_data(data_type):
    """
    Reads the data from the files and returns them as a dataframe.

    :param data_type: Data to load
    :return: the loaded dataframes
    """
    if data_type == str_zjs:
        zjs = pd.DataFrame(json.load(open(str_data_path +'zjs_strict.json', 'r', encoding="utf-8")))
        zjs = zjs[zjs['ip_cleared']==True]
        return zjs
    if data_type == str_benchathon:
        bench = pd.DataFrame(json.load(open(str_data_path +'benchathon.json', 'r', encoding="utf-8")))
        return bench
    return None

def create_dir(directory_name, delete=True):
    """
    Creates a directory if it doesn't exist

    :param directory_name: name / path to create
    :param delete: if True, then an old directory with same name will be delted
    """
    if delete and exists(directory_name):
        shutil.rmtree(directory_name)
    if not exists(directory_name):
        os.makedirs(directory_name)

def save_final_dataframe(result_file):
    """
    Creates the final dataframes from the temp files saved in between. Extends if exists.

    :param result_file: The name of the final dataframe file
    :return: The final dataframe (only the new one created)
    """
    var_filename, state_dict_filename = result_file + '_var', result_file + '_sd'
    os.remove(state_dict_filename)
    cur_filename = var_filename
    cur_result_file = result_file

    var = json.load(open(cur_filename))
    var = pd.DataFrame.from_dict(var)

    # append if exists
    if os.path.exists(cur_result_file):
        old = pd.read_json(cur_result_file)
        old = pd.concat([old, var], ignore_index=True)
    else:
        old = var

    old.to_json(cur_result_file)
    os.remove(cur_filename)
    return var

def load_state(result_file):
    """
    Loads the state from a json file

    :param result_file: filename for loading
    :return: The loaded state_dict if found, None otherwise
    """
    state_dict = None
    state_dict_filename = result_file + '_sd'
    # check if there was some work in progress
    if os.path.exists(state_dict_filename):
        state_dict = json.load(open(state_dict_filename))
    return state_dict

def save_batch_and_state(batch, result_file, state_dict):
    """
    Saved both the batch and the state_dict to temp files. Extends old files if they exist.

    :param batch: The batch to save
    :param result_file: The filename to save the files
    :param state_dict: The state_dict to save
    """
    var_filename, state_dict_filename = result_file + '_var', result_file + '_sd'
    cur_filename = var_filename

    var = None
    if os.path.exists(cur_filename):
        var = json.load(open(cur_filename))
    if var is not None:
        var = {key: batch[key] + var[key] for key in batch}
    else:
        var = batch
    current_result_path = '/'.join(cur_filename.split('/')[:-1])
    if not os.path.exists(current_result_path):
        os.makedirs(current_result_path)
    with open(cur_filename, "w") as outfile:
        json.dump(var, outfile)

    with open(state_dict_filename, "w") as outfile:
        json.dump(state_dict, outfile)

def get_model_and_tokenizer(model_name):
    """
    Loads the model and tokenizer for the given model name.

    :param model_name: Name of the model
    :return: model, tokenizer
    """
    model, tokenizer = None, None
    if model_name == str_model_name_gemma:
        model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="auto", token=hf_token,
                                                     cache_dir=hf_cache)
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token, cache_dir=hf_cache)
    if model_name == str_model_name_gptoss:
        quantization_config = Mxfp4Config()
        model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="auto",
                                                     token=hf_token, cache_dir=hf_cache, quantization_config=quantization_config)
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token, cache_dir=hf_cache)
    if model_name == str_model_name_llama:
        model = AutoModelForCausalLM.from_pretrained(model_name, dtype="auto", device_map="auto", token=hf_token, cache_dir=hf_cache)
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token, cache_dir=hf_cache)
    return model, tokenizer

def create_watermark_data(model, tokenizer, model_name, data_type):
    """
    Generates the texts for the results, with and without the watermark. Saves the results into files.

    :param model: The loaded model
    :param tokenizer: The loaded tokenizer
    :param model_name: The name of the model
    :param data_type: The data type for data loading
    """
    m_id = model_name.split('/')[-1][:5]

    # Transformers config
    transformers_config = TransformersConfig(
        model=model,
        tokenizer=tokenizer,
        vocab_size= len(tokenizer),
        device=device,
        max_new_tokens=16000,
        min_length=300,
        temperature=1.0,
        do_sample=True)

    if m_id == 'Qwen3':
        # best practice values from model card
        transformers_config = TransformersConfig(
            model=model, tokenizer=tokenizer, vocab_size= len(tokenizer),
            device=device, max_new_tokens=16000, min_length=300, do_sample=True,
            temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,repetition_penalty=1.0)

    # read data
    data = read_complete_data(data_type)
    data = Dataset.from_pandas(data)

    save_path = str_results_path + data_type + '_'+m_id+ '.json'
    try:
        res = pd.read_json(save_path)
    except FileNotFoundError:
        create_dir(directory_name=str_results_path, delete=False)

        watermarkers = {key: AutoWatermark.load(key, algorithm_config='markllm/config/' + key + '.json',
                                                transformers_config=transformers_config) for key in watermarks}

        dataset = StatefulDataLoader(data, batch_size=dataloader_batchsize, num_workers=dataloader_num_workers)
        state_dict = load_state(save_path)
        if state_dict is not None:
            dataset.load_state_dict(state_dict)
        for batch in dataset:
            batch_res = generate_results(batch, watermarkers, tokenizer, model_name=model_name)
            save_batch_and_state(batch=batch_res, result_file=save_path, state_dict=dataset.state_dict())
        res = save_final_dataframe(result_file=save_path)
    for wm in watermarks:
        res[wm] = res[wm+str_watermarked_score].apply(lambda x:x['score'])
        print(res[[wm, wm+str_watermarked_length]].corr())

def is_english(text):
    """
    Checks if a text is english.

    :param text: The text to check
    :return: True or False
    """
    lang, _ = langid.classify(text)
    return lang == "en"

def get_input(row, model_name, tokenizer):
    """
    Formats the input texts and applies the chat template.

    :param row: Data to work on
    :param model_name: The name of the model for the chat template
    :param tokenizer:  The loaded tokenizer
    :return: The finished prompt
    """
    instruct_prompt = instruct_exams + row['fall']
    system_prompt = system_exams
    # Prompt
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruct_prompt},
    ]
    if model_name == str_model_name_gemma:
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                                        enable_thinking=True)
    else:
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return prompt

def generate_results(batch, watermarkers, tokenizer, model_name):
    """
    Generates the texts for a batch

    :param batch: The batch of data.
    :param watermarkers: The watermarking algorithms
    :param tokenizer: The loaded tokenizer
    :param model_name: The model name
    :return: thhe processed batch
    """
    batch_df = pd.DataFrame(batch)
    batch_df[str_input_text] = batch_df.apply(
        lambda x: get_input(x, model_name, tokenizer), 1)
    batch_df[str_input_length] = batch_df.apply(
        lambda x: tokenizer(x[str_input_text], return_tensors="pt", add_special_tokens=False)["input_ids"].shape[-1],1)
    batch_df[str_gold_length] = batch_df.apply(
        lambda x: tokenizer(x['musterloesung'], return_tensors="pt", add_special_tokens=False)["input_ids"].shape[-1],1)

    # unwatermarked texts are always created the same / use the same code, so just take one of the watermarkers
    var_watermarker = watermarkers[list(watermarkers.keys())[0]]

    batch_df = watermark_with_retry(bat=batch_df, wm_func=var_watermarker.generate_unwatermarked_text,
                                 source_col=str_input_text,target_col=str_unwatermarked_text,
                                    target_length_col=str_unwatermarked_length, tokenizer=tokenizer, model_name=model_name)

    for wm_key in watermarkers:
        if wm_key == 'EXP2' and model_name == str_model_name_llama:
            continue
        watermark = watermarkers[wm_key]
        # score watermarked lösung
        batch_df = watermark_with_retry(bat=batch_df, wm_func=watermark.generate_watermarked_text,
                                        source_col=str_input_text, target_col=wm_key+str_watermarked_text,
                                        target_length_col=wm_key+str_watermarked_length, tokenizer=tokenizer,
                                        target_score_col=wm_key+str_watermarked_score,
                                        wm_detect_func=watermark.detect_watermark, model_name=model_name)


        # evtl. resamplen
    return batch_df.to_dict("list")

def watermark_with_retry(bat, model_name, source_col, target_col, target_length_col, tokenizer, wm_func, wm_detect_func=None, target_score_col=None):
    """
    Uses the markllm library to create watermarked text.

    :param bat: The batch of data
    :param model_name: The model name
    :param source_col: The column name of the source text
    :param target_col: The column name of the target text
    :param target_length_col: The column name of the target length
    :param tokenizer: The loaded tokenizer
    :param wm_func: The function for watermarking
    :param wm_detect_func: The detection function for watermarking
    :param target_score_col: The column name of the target score
    :return: The processed batch
    """
    forbidden_indicators = ['<|channel|>'] # tags found in erroneous answers
    bat[target_col] = bat.apply(lambda x: postprocess_generated_text(wm_func(x[source_col]), model_name=model_name), 1)

    def get_watermark_score(row):
        scores = wm_detect_func(row[target_col])
        scores["is_watermarked"] = 1 if scores["is_watermarked"] else 0
        return scores

    if wm_detect_func is not None:
        bat[target_score_col] = bat.apply(lambda x: get_watermark_score(x), 1)

    for _ in range(5):
        # retry if necessary for language
        if wm_detect_func is not None:
            bat[target_col] = bat.apply(lambda x:
                                        postprocess_generated_text(wm_func(x[source_col]), model_name=model_name)
                                        if (any(elem in x[target_col] for elem in forbidden_indicators) or x[target_score_col]["is_watermarked"]==0)  or is_english(x[target_col][:300])
                                        else x[target_col]
                                        , 1)
            bat[target_score_col] = bat.apply(lambda x: get_watermark_score(x), 1)
        else:
            bat[target_col] = bat.apply(lambda x:
                                        postprocess_generated_text(wm_func(x[source_col]), model_name=model_name)
                                        if any(elem in x[target_col] for elem in forbidden_indicators)  or is_english(x[target_col][:300])
                                        else x[target_col]
                                        , 1)

    bat[target_length_col] = bat.apply(
        lambda x: tokenizer(x[target_col], return_tensors="pt", add_special_tokens=False)["input_ids"].shape[-1], 1)

    return bat

def postprocess_generated_text(text, model_name):
    """
    Removes tokens from the generated results which don't belong to the answer.

    :param text: Text to postprocess
    :param model_name: The model name (because of model specific tempaltes)
    :return: The processed text
    """
    if model_name == str_model_name_gptoss:
        text = text.split("<|channel|>final<|message|>")[-1]
        text = text.split("<|return|>")[0].split("<|end|>")[0].strip()
    if model_name == str_model_name_llama:
        text = text.split("<|eot_id|>")[0].strip()
    if model_name == str_model_name_gemma:
        text = text.split("<channel|>")[-1]
        text = text.split("<turn|>")[0].strip()

    return text

def finalise_result_data():
    """
    Prints some datasets statistics and adjusts one column of the results.
    """
    create_dir(str_results_path+'/final', delete=False)
    for model in model_names:
        m_id = model.split('/')[-1][:5]
        print(m_id)

        for data_type in data_types:
            print(d_type)
            data = pd.read_json(str_results_path + data_type + '_' + m_id + '.json')
            print('Length unwatermarked:', data[str_unwatermarked_length].mean())
            print('Standard Deviation:', data[str_unwatermarked_length].std())

            for wm in watermarks:
                if wm == 'EXP2' and model == str_model_name_llama:
                    continue
                print(wm)
                data[wm + str_watermarked_score] = data[wm + str_watermarked_score].apply(lambda d: d['is_watermarked'])
                print('Percentage watermarked:', data[wm + str_watermarked_score].sum() / len(data))
                print('Length:', data[wm + str_watermarked_length].mean())
                print('Standard Deviation:', data[wm + str_watermarked_length].std())
                if data[wm + str_watermarked_score].sum() / len(data) < 1:
                    print(data[[wm + str_watermarked_score, wm + str_watermarked_length]].corr())
            data.to_json(str_results_path+'final/'+data_type+'_'+m_id+'.json')

if __name__ == '__main__':
    for m_name in model_names:
        for d_type in data_types:
            mod, tok = get_model_and_tokenizer(m_name)
            create_watermark_data(model=mod, tokenizer=tok, model_name=m_name, data_type=d_type)

    finalise_result_data()


