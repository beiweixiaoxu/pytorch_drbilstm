"""
Preprocessor and dataset definition for NLI.
"""
# Aurelien Coet, 2019.

import string
import torch
import numpy as np
import random
from collections import Counter
from tqdm import tqdm
from torch.utils.data import Dataset
class Preprocessor(object):
    """
    Preprocessor class for Natural Language Inference datasets.

    The class can be used to read NLI datasets, build worddicts for them
    and transform their premises, hypotheses and labels into lists of
    integer indices.
    """
    def __init__(self,
                 lowercase=False,
                 ignore_punctuation=False,
                 num_words=None,
                 labeldict={},
                 bos=None,
                 eos=None,
                 aug_rate = 0.5,
                 aug_drop_p = 0.5):
        self.lowercase = lowercase
        self.ignore_punctuation = ignore_punctuation
        self.num_words = num_words
        self.labeldict = labeldict
        # self.stopwords = set(stopwords.words('english'))
        self.bos = bos
        self.eos = eos
        self.aug_rate = aug_rate
        self.aug_drop_p = aug_drop_p

    def read_data(self, filepath, train = False):
        with open(filepath, "r", encoding="utf8") as input_data:
            ids, premises, hypotheses, labels = [], [], [], []

            # Translation tables to remove parentheses and punctuation from
            # strings.
            parentheses_table = str.maketrans({"(": None, ")": None})
            punct_table = str.maketrans({key: " "
                                         for key in string.punctuation})

            # Ignore the headers on the first line of the file.
            next(input_data)

            for line in input_data:
                line = line.strip().split("\t")
                # Ignore sentences that have no gold label.
                if line[0] == "-":
                    continue

                pair_id = line[7]
                premise = line[1]
                hypothesis = line[2]

                # Remove '(' and ')' from the premises and hypotheses.
                premise = premise.translate(parentheses_table)
                hypothesis = hypothesis.translate(parentheses_table)

                if train == True:
                    premise, hypothesis = self.aug_function(premise, hypothesis, self.aug_rate, self.aug_drop_p)

                if self.lowercase:
                    premise = premise.lower()
                    hypothesis = hypothesis.lower()

                if self.ignore_punctuation:
                    premise = premise.translate(punct_table)
                    hypothesis = hypothesis.translate(punct_table)
                # Each premise and hypothesis is split into a list of words.

                if type(premise) == str:
                    premise = [premise]
                    hypothesis = [hypothesis]
                for idx in range(len(premise)):
                    p = premise[idx]
                    h = hypothesis[idx]
                    premises.append([w for w in p.rstrip().split()])
                    hypotheses.append([w for w in h.rstrip().split()])
                    labels.append(line[0])
                    ids.append(pair_id)
            return {"ids": ids,
                    "premises": premises,
                    "hypotheses": hypotheses,
                    "labels": labels}

    def aug_function(self, premise, hypothesis, aug_rate, aug_drop_p = 0.5):
        is_aug = random.random()
        if is_aug < aug_rate:
            # aug
            rate = random.random()
            if rate > 0.5:
                auged_premise = self.shuffle(premise)
                auged_hypothesis = self.shuffle(hypothesis)
            else:
                auged_premise = self.dropout(premise,aug_drop_p)
                auged_hypothesis = self.dropout(hypothesis,aug_drop_p)
            return [premise, auged_premise], [hypothesis, auged_hypothesis]
        else:
            return premise, hypothesis

    def shuffle(self, text):
        text = np.random.permutation(text.rstrip().split())
        return ' '.join(text)

    def dropout(self, text, p=0.3):
        text = text.rstrip().split()
        len_ = len(text)
        indexs = np.random.choice(len_, int(len_ * p))
        for i in indexs:
            text[i] = '_OOV_' #
        return ' '.join(text)

    def build_worddict(self, data):
        """
        Build a dictionary associating words to unique integer indices for
        some dataset. The worddict can then be used to transform the words
        in datasets to their indices.

        Args:
            data: A dictionary containing the premises, hypotheses and
                labels of some NLI dataset, in the format returned by the
                'read_data' method of the Preprocessor class.
        """
        words = []
        [words.extend(sentence) for sentence in data["premises"]]
        [words.extend(sentence) for sentence in data["hypotheses"]]

        counts = Counter(words)

        del counts["_OOV_"]

        num_words = self.num_words

        if self.num_words is None:
            num_words = len(counts)
        self.worddict = {}
        # Special indices are used for padding, out-of-vocabulary words, and
        # beginning and end of sentence tokens.
        self.worddict["_PAD_"] = 0
        self.worddict["_OOV_"] = 1
        offset = 2
        if self.bos:
            self.worddict["_BOS_"] = 2
            offset += 1
        if self.eos:
            self.worddict["_EOS_"] = 3
            offset += 1


        for i, word in enumerate(counts.most_common(num_words)):
            self.worddict[word[0]] = i + offset

        if self.labeldict == {}:
            label_names = set(data["labels"])
            self.labeldict = {label_name: i
                              for i, label_name in enumerate(label_names)}

    def words_to_indices(self, sentence, lowercase=False, rm_stopwords=False):
        indices = []
        # Include the beggining of sentence token at the start of the sentence
        # if one is defined.
        if self.bos:
            indices.append(self.worddict["_BOS_"])

        for word in sentence:
            if lowercase:
                word = word.lower()
            # if rm_stopwords and word in self.stopwords:
            #     continue
            if word in self.worddict:  # 这里有两种情况: 1.数据增强的时候，人为加入的_OOV_标识符(仅train) 2.不在worddict中的字符(valid和test)
                index = self.worddict[word]
            else:
                index = self.worddict["_OOV_"]
            indices.append(index)
        # Add the end of sentence token at the end of the sentence if one
        # is defined.
        if self.eos:
            indices.append(self.worddict["_EOS_"])

        return indices

    def indices_to_words(self, indices):
        return [list(self.worddict.keys())[list(self.worddict.values())
                                           .index(i)]
                for i in indices]

    def prepare_data(self, data):
        """
        Transform the words in the premises and hypotheses of a dataset, as
        well as their associated labels, to integer indices.

        Args:
            data: A dictionary containing lists of premises, hypotheses
                and labels, in the format returned by the 'read_data'
                method of the Preprocessor class.

        Returns:
            A dictionary containing the transformed premises, hypotheses and
            labels.
        """
        prepared_data = {"ids": [],
                         "premises": [],
                         "hypotheses": [],
                         "le_premises": [],
                         "le_hypotheses": [],
                         "labels": []}

        tqdm_iterator = tqdm(data["premises"], desc="** Preprocessing data: ")
        for i, premise in enumerate(tqdm_iterator):
            # Ignore sentences that have a label for which no index was
            # defined in 'labeldict'.
            label = data["labels"][i]
            if label not in self.labeldict and label != "hidden":
                continue
            prepared_data["ids"].append(data["ids"][i])

            if label == "hidden":
                prepared_data["labels"].append(-1)
            else:
                prepared_data["labels"].append(self.labeldict[label])

            indices = self.words_to_indices(premise)
            prepared_data["premises"].append(indices)

            indices = self.words_to_indices(data["hypotheses"][i])
            prepared_data["hypotheses"].append(indices)
            prem_indices = self.words_to_indices(premise,
                                                 lowercase=True)
            hyp_indices = self.words_to_indices(data["hypotheses"][i],
                                                lowercase=True)
            prepared_data["le_premises"].append(prem_indices)
            prepared_data["le_hypotheses"].append(hyp_indices)
        return prepared_data

    def build_embedding_matrix(self, embeddings_file):
        """
        Build an embedding matrix with pretrained weights for the object's
        worddict.

        Args:
            embeddings_file: A file containing pretrained word embeddings.

        Returns:
            A numpy matrix of size (num_words+n_special_tokens, embedding_dim)
            containing pretrained word embeddings (the +n_special_tokens is for
            the padding and out-of-vocabulary tokens, as well as BOS and EOS if
            they're used).
        """
        embeddings = {}
        tmp_matrix = []
        with open(embeddings_file, "r", encoding="utf8") as input_data:
            for line in input_data:
                line = line.split()

                try:
                    # Check that the second element on the line is the start
                    # of the embedding and not another word. Necessary to
                    # ignore multiple word lines.
                    float(line[1])
                    word = line[0]
                    if word in self.worddict:
                        # Load the word embeddings in a dictionnary.
                        embedding = np.array(line[1:], dtype=float)
                        embeddings[word] = embedding
                        # A temporary numpy matrix is used to save the
                        # embeddings and compute the mean and variance
                        # of each of their dimensions later.
                        tmp_matrix.append(embedding)

                # Ignore lines corresponding to multiple words separated
                # by spaces.
                except ValueError:
                    continue

        num_words = len(self.worddict)
        embedding_dim = len(list(embeddings.values())[0])
        embedding_matrix = np.zeros((num_words, embedding_dim))

        # The temporary embedding matrix built in the previous step
        # is used to compute the mean and std of each dimension of
        # the embeddings in the input file.
        tmp_matrix = np.array(tmp_matrix, dtype=float)
        means = []
        std_deviations = [] 
        for dimension in range(tmp_matrix.shape[1]):
            means.append(np.mean(tmp_matrix[:, dimension]))
            std_deviations.append(np.std(tmp_matrix[:, dimension]))

        # Actual building of the embedding matrix.
        missed = 0
        for word, i in self.worddict.items():
            if word in embeddings:
                embedding_matrix[i] = embeddings[word]
            else:
                if word == "_PAD_":
                    continue
                missed += 1
                # Out of vocabulary words are initialised with random gaussian
                # samples. The value for each dimension of the out of vocabulary
                # word is generated randomly with a Gaussian and the mean and
                # std values computed earlier.
                embedding_matrix[i] = np.array([np.random.normal(loc=mean,
                                                                 scale=std_deviations[i])
                                                for i, mean in enumerate(means)])
        print("* Number of words in the worddict absent from the pre-trained\
 embeddings in file {}: {}".format(embeddings_file, missed))

        return embedding_matrix


class NLIDataset(Dataset):
    """
    Dataset class for Natural Language Inference datasets.

    The class can be used to read preprocessed datasets where the premises,
    hypotheses and labels have been transformed to unique integer indices
    (this can be done with the 'preprocess_data' script in the 'scripts'
    folder of this repository).
    """

    def __init__(self,
                 data,
                 padding_idx=0,
                 max_premise_length=None,
                 max_hypothesis_length=None):
        """
        Args:
            data: A dictionary containing the preprocessed premises,
                hypotheses and labels of some dataset.
            padding_idx: An integer indicating the index being used for the
                padding token in the preprocessed data. Defaults to 0.
            max_premise_length: An integer indicating the maximum length
                accepted for the sequences in the premises. If set to None,
                the length of the longest premise in 'data' is used.
                Defaults to None.
            max_hypothesis_length: An integer indicating the maximum length
                accepted for the sequences in the hypotheses. If set to None,
                the length of the longest hypothesis in 'data' is used.
                Defaults to None.
        """
        self.premises_lengths = [len(seq) for seq in data["premises"]]
        self.max_premise_length = max_premise_length
        if self.max_premise_length is None:
            self.max_premise_length = max(self.premises_lengths)
        
        self.le_premises_lengths = [len(seq) for seq in data["le_premises"]]

        self.hypotheses_lengths = [len(seq) for seq in data["hypotheses"]]
        self.max_hypothesis_length = max_hypothesis_length
        if self.max_hypothesis_length is None:
            self.max_hypothesis_length = max(self.hypotheses_lengths)

        self.le_hypotheses_lengths = [len(seq) for seq in data["le_hypotheses"]]

        self.num_sequences = len(data["premises"])

        self.data = {"ids": [],
                     "premises": torch.ones((self.num_sequences,
                                             self.max_premise_length),
                                            dtype=torch.long) * padding_idx,
                     "hypotheses": torch.ones((self.num_sequences,
                                               self.max_hypothesis_length),
                                              dtype=torch.long) * padding_idx,
                     "le_premises": torch.ones((self.num_sequences,
                                                self.max_premise_length),
                                               dtype=torch.long) * padding_idx,
                     "le_hypotheses": torch.ones((self.num_sequences,
                                                  self.max_hypothesis_length),
                                                 dtype=torch.long) * padding_idx,
                     "labels": torch.tensor(data["labels"], dtype=torch.long)}

        for i, premise in enumerate(data["premises"]):
            self.data["ids"].append(data["ids"][i])
            
            end = min(len(premise), self.max_premise_length)
            self.data["premises"][i][:end] = torch.tensor(premise[:end])

            le_premise = data["le_premises"][i]
            end = min(len(le_premise), self.max_premise_length)
            self.data["le_premises"][i][:end] = torch.tensor(le_premise[:end])

            hypothesis = data["hypotheses"][i]
            end = min(len(hypothesis), self.max_hypothesis_length)
            self.data["hypotheses"][i][:end] = torch.tensor(hypothesis[:end])

            le_hypothesis = data["le_hypotheses"][i]
            end = min(len(le_hypothesis), self.max_hypothesis_length)
            self.data["le_hypotheses"][i][:end] = torch.tensor(le_hypothesis[:end])

    def __len__(self):
        return self.num_sequences

    def __getitem__(self, index):
        return {"id": self.data["ids"][index],
                "premise": self.data["premises"][index],
                "premise_length": min(self.premises_lengths[index],
                                      self.max_premise_length),
                "le_premise": self.data["le_premises"][index],
                "le_premise_length": min(self.le_premises_lengths[index],
                                         self.max_premise_length),
                "hypothesis": self.data["hypotheses"][index],
                "hypothesis_length": min(self.hypotheses_lengths[index],
                                         self.max_hypothesis_length),
                "le_hypothesis": self.data["le_hypotheses"][index],
                "le_hypothesis_length": min(self.le_hypotheses_lengths[index],
                                            self.max_hypothesis_length),
                "label": self.data["labels"][index]}
