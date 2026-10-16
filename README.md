# An Exploratory Study on the Impact of  LLM Text Watermarking on Legal Reasoning Qualit

This repository contains the code for the paper *An Exploratory Study on the Impact of 
LLM Text Watermarking on Legal Reasoning Quality* published at Jurix 2026. 

Watermarking algorithms constitute a promising approach for promoting the transparency of AI-generated texts. 
However, since these algorithms affect text generation, losses in output quality might outweigh transparency gains, especially in areas as sensitive as the legal domain. 
The paper at hand explores the impact of two watermarking algorithms (KGW and EXP) on German open text legal subsumption tasks within the BenGER Benchmark performed by three open-source LLMs (Llama, Gemma and GPT-OSS). 
While watermarking without substantial loss of output quality can be achieved in principle, model certainty settings desirable in the legal domain conflict with the principles underlying watermarking algorithms, thus potentially hindering effective watermark embedding.

For examples of the subsumptive legal reasoning tasks, see the [BenGER repo](https://github.com/SebastianNagl/benger-platform).

Citation:
```
@InProceedings{SteffesEtAl2026JurixWatermarking,
  title		= {An Exploratory Study on the Impact of LLM Text Watermarking on Legal Reasoning Quality},
  author	= {Steffes, Bianca and Sasdelli, Diogo and Nagl, Sebastian and Herrmann, Jessica},
  booktitle	= {{Legal Knowledge and Information Systems - Proceedings of the 39th International Conference 
                on  Legal Knowledge and Information Systems – JURIX 2026}},
  year		= {2026},
}
```