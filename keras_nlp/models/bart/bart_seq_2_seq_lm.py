# Copyright 2022 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""BART Seq2Seq LM (Language Model)."""

import copy

import tensorflow as tf
from tensorflow import keras

from keras_nlp.api_export import keras_nlp_export
from keras_nlp.models.bart.bart_backbone import BartBackbone
from keras_nlp.models.bart.bart_presets import backbone_presets
from keras_nlp.models.bart.bart_seq_2_seq_lm_preprocessor import (
    BartSeq2SeqLMPreprocessor,
)
from keras_nlp.models.task import Task
from keras_nlp.samplers.serialization import get as get_sampler
from keras_nlp.utils.keras_utils import is_xla_compatible
from keras_nlp.utils.python_utils import classproperty
from keras_nlp.utils.tensor_utils import tensor_to_string_list


@keras_nlp_export("keras_nlp.models.BartSeq2SeqLM")
class BartSeq2SeqLM(Task):
    """An end-to-end BART model for seq2seq language modeling.

    A seq2seq language model (LM) is an encoder-decoder model which is used for
    conditional text generation. The encoder is given a "context" text (fed to
    the encoder), and the decoder predicts the next token based on both the
    encoder inputs and the previous tokens. You can finetune `BartSeq2SeqLM` to
    generate text for any seq2seq task (e.g., translation or summarization).

    This model has a `generate()` method, which generates text based on
    encoder inputs and an optional prompt for the decoder. The generation
    strategy used is controlled by an additional `sampler` argument passed to
    `compile()`. You can recompile the model with different `keras_nlp.samplers`
    objects to control the generation. By default, `"top_k"` sampling will be
    used.

    This model can optionally be configured with a `preprocessor` layer, in
    which case it will automatically apply preprocessing to string inputs during
    `fit()`, `predict()`, `evaluate()` and `generate()`. This is done by default
    when creating the model with `from_preset()`.

    Disclaimer: Pre-trained models are provided on an "as is" basis, without
    warranties or conditions of any kind. The underlying model is provided by a
    third party and subject to a separate license, available
    [here](https://github.com/facebookresearch/fairseq/).

    Args:
        backbone: A `keras_nlp.models.BartBackbone` instance.
        preprocessor: A `keras_nlp.models.BartSeq2SeqLMPreprocessor` or `None`.
            If `None`, this model will not apply preprocessing, and inputs
            should be preprocessed before calling the model.

    Examples:

    Use `generate()` to do text generation, given an input context.
    ```python
    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset("bart_base_en")
    bart_lm.generate("The quick brown fox", max_length=30)

    # Generate with batched inputs.
    bart_lm.generate(["The quick brown fox", "The whale"], max_length=30)
    ```

    Compile the `generate()` function with a custom sampler.
    ```python
    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset("bart_base_en")
    bart_lm.compile(sampler="greedy")
    bart_lm.generate("The quick brown fox", max_length=30)
    ```

    Use `generate()` with encoder inputs and an incomplete decoder input (prompt).
    ```python
    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset("bart_base_en")
    bart_lm.generate(
        {
            "encoder_text": "The quick brown fox",
            "decoder_text": "The fast"
        }
    )
    ```

    Use `generate()` without preprocessing.
    ```python
    # Preprocessed inputs, with encoder inputs corresponding to
    # "The quick brown fox", and the decoder inputs to "The fast". Use
    # `"padding_mask"` to indicate values that should not be overridden.
    prompt = {
        "encoder_token_ids": tf.constant([[0, 133, 2119, 6219, 23602, 2, 1, 1]]),
        "encoder_padding_mask": tf.constant(
            [[True, True, True, True, True, True, False, False]]
        ),
        "decoder_token_ids": tf.constant([[2, 0, 133, 1769, 2, 1, 1]]),
        "decoder_padding_mask": tf.constant([[True, True, True, True, False, False]])
    }

    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset(
        "bart_base_en",
        preprocessor=None,
    )
    bart_lm.generate(prompt)
    ```

    Call `fit()` on a single batch.
    ```python
    features = {
        "encoder_text": ["The quick brown fox jumped.", "I forgot my homework."],
        "decoder_text": ["The fast hazel fox leapt.", "I forgot my assignment."]
    }
    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset("bart_base_en")
    bart_lm.fit(x=features, batch_size=2)
    ```

    Call `fit()` without preprocessing.
    ```python
    x = {
        "encoder_token_ids": tf.constant([[0, 133, 2119, 2, 1]] * 2),
        "encoder_padding_mask": tf.constant([[1, 1, 1, 1, 0]] * 2),
        "decoder_token_ids": tf.constant([[2, 0, 133, 1769, 2]] * 2),
        "decoder_padding_mask": tf.constant([[1, 1, 1, 1, 1]] * 2),
    }
    y = tf.constant([[0, 133, 1769, 2, 1]] * 2)
    sw = tf.constant([[1, 1, 1, 1, 0]] * 2)

    bart_lm = keras_nlp.models.BartSeq2SeqLM.from_preset(
        "bart_base_en",
        preprocessor=None,
    )
    bart_lm.fit(x=x, y=y, sample_weight=sw, batch_size=2)
    ```

    Custom backbone and vocabulary.
    ```python
    features = {
        "encoder_text": [" afternoon sun"],
        "decoder_text": ["noon sun"],
    }
    vocab = {
        "<s>": 0,
        "<pad>": 1,
        "</s>": 2,
        "Ġafter": 5,
        "noon": 6,
        "Ġsun": 7,
    }
    merges = ["Ġ a", "Ġ s", "Ġ n", "e r", "n o", "o n", "Ġs u", "Ġa f", "no on"]
    merges += ["Ġsu n", "Ġaf t", "Ġaft er"]

    tokenizer = keras_nlp.models.BartTokenizer(
        vocabulary=vocab,
        merges=merges,
    )
    preprocessor = keras_nlp.models.BartSeq2SeqLMPreprocessor(
        tokenizer=tokenizer,
        encoder_sequence_length=128,
        decoder_sequence_length=128,
    )
    backbone = keras_nlp.models.BartBackbone(
        vocabulary_size=50265,
        num_layers=6,
        num_heads=12,
        hidden_dim=768,
        intermediate_dim=3072,
        max_sequence_length=128,
    )
    bart_lm = keras_nlp.models.BartSeq2SeqLM(
        backbone=backbone,
        preprocessor=preprocessor,
    )
    bart_lm.fit(x=features, batch_size=2)
    ```
    """

    def __init__(
        self,
        backbone,
        preprocessor=None,
        **kwargs,
    ):
        inputs = backbone.input
        x = backbone(inputs)["decoder_sequence_output"]
        # Use token embedding weights to project from the token representation
        # to vocabulary logits.
        outputs = tf.matmul(
            x,
            backbone.token_embedding.embeddings,
            transpose_b=True,
        )

        # Instantiate using Functional API Model constructor.
        super().__init__(
            inputs=inputs,
            outputs=outputs,
            include_preprocessing=preprocessor is not None,
            **kwargs,
        )

        self.backbone = backbone
        self.preprocessor = preprocessor
        self.generate_function = None
        self._sampler = None

        # Default compilation
        self.compile(
            loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),
            optimizer=keras.optimizers.Adam(2e-5),
            metrics=[keras.metrics.SparseCategoricalAccuracy()],
            jit_compile=is_xla_compatible(self),
        )

    @classproperty
    def presets(cls):
        return copy.deepcopy(backbone_presets)

    @classproperty
    def backbone_cls(cls):
        return BartBackbone

    @classproperty
    def preprocessor_cls(cls):
        return BartSeq2SeqLMPreprocessor

    def call_decoder_with_cache(
        self,
        encoder_hidden_states,
        encoder_padding_mask,
        decoder_token_ids,
        self_attention_cache=None,
        self_attention_cache_update_index=None,
        cross_attention_cache=None,
        cross_attention_cache_update_index=None,
    ):
        """Forward pass with a key/value caches for generative decoding..

        `call_decoder_with_cache` adds an additional inference-time forward pass
        for the model for seq2seq text generation. Unlike calling the model
        directly, this method does two things to optimize text generation:

        - Allows caching previous key/value tensors in the decoder's
          self-attention layer to avoid recomputing the outputs of seen tokens.
        - Allows caching key/value tensors in the decoder's cross-attention
          layer to avoid recomputing the encoder outputs.

        Args:
            encoder_hidden_states: a dense float Tensor of shape
                `(batch_size, encoder_sequence_length, hidden_dim)`. The
                sequence of hidden states at the output of the encoder's last
                layer.
            encoder_padding_mask: a dense float Tensor of shape
                `(batch_size, encoder_sequence_length)`. The padding mask for
                the encoder input.
            decoder_token_ids: a dense int Tensor of shape
                `(batch_size, max_length)`. Input token ids to be fed to
                the decoder.
            self_attention_cache: a dense float Tensor of shape
                `(batch_size, num_layers, 2, max_length, num_heads, key_dims)`.
                The cached key/value tensors of previously seen tokens in the
                decoder's self-attention layer.
            self_attention_cache_update_index: an int or int Tensor, the index
                at which to update the `self_attention_cache`. Usually, this is
                the index of the current token being processed during decoding.
            cross_attention_cache: a dense float Tensor of shape
                `(batch_size, num_layers, 2, encoder_sequence_length, num_heads, key_dims)`.
                The cached key/value tensors of the encoder outputs in the
                decoder's cross-attention layer.
            cross_attention_cache_update_index: an int or int Tensor, the index
                at which to update the `cross_attention_cache`. Usually, this is
                either `0` (compute the entire `cross_attention_cache`), or
                `None` (reuse a previously computed `cross_attention_cache`).

        Returns:
            A `(logits, hidden_states, self_attention_cache, cross_attention_cache)`
            tuple, where `logits` is the language model logits for the input
            `decoder_token_ids`, `hidden_states` is the final hidden
            representation of the input tokens, `self_attention_cache` is the
            key/value cache in the decoder's self-attention layer and
            `cross_attention_cache` is the key/value cache in the decoder's
            cross-attention layer.
        """
        # Embedding layers.
        token_embedding = self.backbone.get_layer("token_embedding")(
            decoder_token_ids
        )
        position_embedding = self.backbone.get_layer(
            "decoder_position_embedding"
        )(token_embedding, start_index=self_attention_cache_update_index)

        # Sum, normalize and apply dropout to embeddings.
        x = self.backbone.get_layer("decoder_embeddings_add")(
            (token_embedding, position_embedding)
        )
        x = self.backbone.get_layer("decoder_embeddings_layer_norm")(x)
        x = self.backbone.get_layer("decoder_embeddings_dropout")(x)

        # Every decoder layer has a separate cache for the self-attention layer
        # and the cross-attention layer. We update all of them separately.
        self_attention_caches = tf.unstack(self_attention_cache, axis=1)
        cross_attention_caches = tf.unstack(cross_attention_cache, axis=1)
        for i in range(self.backbone.num_layers):
            current_self_attention_cache = self_attention_caches[i]
            current_cross_attention_cache = cross_attention_caches[i]

            (
                x,
                next_self_attention_cache,
                next_cross_attention_cache,
            ) = self.backbone.get_layer(f"transformer_decoder_layer_{i}")(
                decoder_sequence=x,
                encoder_sequence=encoder_hidden_states,
                encoder_padding_mask=encoder_padding_mask,
                self_attention_cache=current_self_attention_cache,
                self_attention_cache_update_index=self_attention_cache_update_index,
                cross_attention_cache=current_cross_attention_cache,
                cross_attention_cache_update_index=cross_attention_cache_update_index,
            )

            if self_attention_cache_update_index is not None:
                self_attention_caches[i] = next_self_attention_cache
            if cross_attention_cache_update_index is not None:
                cross_attention_caches[i] = next_cross_attention_cache

        if self_attention_cache_update_index is not None:
            self_attention_cache = tf.stack(self_attention_caches, axis=1)
        if cross_attention_cache_update_index is not None:
            cross_attention_cache = tf.stack(cross_attention_caches, axis=1)

        hidden_states = x

        logits = tf.matmul(
            hidden_states,
            self.backbone.get_layer("token_embedding").embeddings,
            transpose_b=True,
        )
        return (
            logits,
            hidden_states,
            self_attention_cache,
            cross_attention_cache,
        )

    def call_encoder(self, token_ids, padding_mask):
        """Does a forward pass on the encoder and returns the encoder output."""

        # Embedding layers.
        token_embedding = self.backbone.get_layer("token_embedding")(token_ids)
        position_embedding = self.backbone.get_layer(
            "encoder_position_embedding"
        )(token_embedding)

        # Sum, normalize and apply dropout to embeddings.
        x = self.backbone.get_layer("encoder_embeddings_add")(
            (token_embedding, position_embedding)
        )
        x = self.backbone.get_layer("encoder_embeddings_layer_norm")(x)
        x = self.backbone.get_layer("encoder_embeddings_dropout")(x)

        # Transformer encoder layers.
        for i in range(self.backbone.num_layers):
            x = self.backbone.get_layer(f"transformer_encoder_layer_{i}")(
                x, padding_mask=padding_mask
            )

        return x

    def _initialize_cache(self, encoder_token_ids, decoder_token_ids):
        """Initializes empty self-attention cache and cross-attention cache."""
        batch_size = tf.shape(encoder_token_ids)[0]
        encoder_max_length = tf.shape(encoder_token_ids)[1]
        decoder_max_length = tf.shape(decoder_token_ids)[1]

        num_layers = self.backbone.num_layers
        num_heads = self.backbone.num_heads
        head_dim = self.backbone.hidden_dim // self.backbone.num_heads

        shape = [
            batch_size,
            num_layers,
            2,
            decoder_max_length,
            num_heads,
            head_dim,
        ]
        self_attention_cache = tf.zeros(shape, dtype=self.compute_dtype)

        shape[3] = encoder_max_length
        cross_attention_cache = tf.zeros(shape, dtype=self.compute_dtype)

        return (self_attention_cache, cross_attention_cache)

    def _build_cache(
        self, encoder_token_ids, encoder_padding_mask, decoder_token_ids
    ):
        """Builds the self-attention cache and the cross-attention cache (key/value pairs)."""
        encoder_hidden_states = self.call_encoder(
            token_ids=encoder_token_ids, padding_mask=encoder_padding_mask
        )
        self_attention_cache, cross_attention_cache = self._initialize_cache(
            encoder_token_ids, decoder_token_ids
        )

        # Seed the self-attention cache and the cross-attention cache.
        (
            _,
            hidden_states,
            self_attention_cache,
            cross_attention_cache,
        ) = self.call_decoder_with_cache(
            encoder_hidden_states=encoder_hidden_states,
            encoder_padding_mask=encoder_padding_mask,
            decoder_token_ids=decoder_token_ids,
            self_attention_cache=self_attention_cache,
            self_attention_cache_update_index=0,
            cross_attention_cache=cross_attention_cache,
            cross_attention_cache_update_index=0,
        )
        return (
            hidden_states,
            encoder_hidden_states,
            self_attention_cache,
            cross_attention_cache,
        )

    def compile(
        self,
        *args,
        run_eagerly=False,
        jit_compile=True,
        sampler="top_k",
        **kwargs,
    ):
        xla_compatible = is_xla_compatible(self)
        super().compile(
            *args,
            run_eagerly=run_eagerly,
            # Only `jit_compile` if not eager and in a compatible environment.
            jit_compile=jit_compile and xla_compatible and not run_eagerly,
            **kwargs,
        )
        self._sampler = get_sampler(sampler)
        # Clear the compiled generate function.
        self.generate_function = None

    def make_generate_function(self):
        """Create or return the compiled generation function."""
        if self.generate_function is not None:
            return self.generate_function

        if self.run_eagerly:
            self.generate_function = self.generate_step
        else:
            # `jit_compile` is a property of keras.Model after TF 2.12.
            # Use `getattr()` for backwards compatibility.
            jit_compile = getattr(self, "jit_compile", True)
            self.generate_function = tf.function(
                self.generate_step, jit_compile=jit_compile
            )
        return self.generate_function

    def generate_step(
        self,
        inputs,
        end_token_id=None,
    ):
        """A compilable generation function for a batch of inputs.

        This function represents the inner, XLA-compilable, generation function
        for a single batch of inputs. Inputs should have the same structure as
        model inputs, a dictionary with keys `"encoder_token_ids"`,
        `"encoder_padding_mask"`, `"decoder_token_ids"` and
        `"decoder_padding_mask"`.

        Args:
            inputs: A dictionary with four keys - `"encoder_token_ids"`,
                `"encoder_padding_mask"`, `"decoder_token_ids"` and
                `"decoder_padding_mask"`, with batched tensor values.
            end_token_id: The id of the end token to stop on. If all
                sequences have produced a new `end_token_id`, generation
                will stop.
        """
        (
            encoder_token_ids,
            encoder_padding_mask,
            decoder_token_ids,
            decoder_padding_mask,
        ) = (
            inputs["encoder_token_ids"],
            inputs["encoder_padding_mask"],
            inputs["decoder_token_ids"],
            inputs["decoder_padding_mask"],
        )

        batch_size = tf.shape(encoder_token_ids)[0]

        # Create and seed cache with a single forward pass.
        (
            hidden_states,
            encoder_hidden_states,
            self_attention_cache,
            cross_attention_cache,
        ) = self._build_cache(
            encoder_token_ids, encoder_padding_mask, decoder_token_ids
        )
        # Compute the lengths of all user inputted tokens ids.
        row_lengths = tf.math.reduce_sum(
            tf.cast(decoder_padding_mask, "int32"), axis=-1
        )
        # Start at the first index that has no user inputted id.
        index = tf.math.reduce_min(row_lengths)

        def next(prompt, cache, index):
            # The cache index is the index of our previous token.
            cache_index = index - 1
            prompt = tf.slice(prompt, [0, cache_index], [-1, 1])

            num_samples = tf.shape(prompt)[0]

            def repeat_tensor(x):
                """Repeats tensors along batch axis to match dim for beam search."""
                if tf.shape(x)[0] == num_samples:
                    return x
                return tf.repeat(x, repeats=num_samples // batch_size, axis=0)

            logits, hidden_states, cache, _ = self.call_decoder_with_cache(
                encoder_hidden_states=repeat_tensor(encoder_hidden_states),
                encoder_padding_mask=repeat_tensor(encoder_padding_mask),
                decoder_token_ids=prompt,
                self_attention_cache=cache,
                self_attention_cache_update_index=cache_index,
                cross_attention_cache=repeat_tensor(cross_attention_cache),
                cross_attention_cache_update_index=None,
            )
            return (
                tf.squeeze(logits, axis=1),
                tf.squeeze(hidden_states, axis=1),
                cache,
            )

        decoder_token_ids = self._sampler(
            next=next,
            prompt=decoder_token_ids,
            cache=self_attention_cache,
            index=index,
            mask=decoder_padding_mask,
            end_token_id=end_token_id,
            hidden_states=hidden_states,
        )

        # Compute an output padding mask with the token ids we updated.
        if end_token_id is not None:
            # Build a mask of `end_token_id` locations not in the original
            # prompt (not in locations where `decoder_padding_mask` is True).
            end_locations = (decoder_token_ids == end_token_id) & (
                ~decoder_padding_mask
            )
            end_locations = tf.cast(end_locations, "int32")
            # Use cumsum to get ones in all locations after `end_locations`.
            overflow = tf.math.cumsum(end_locations, exclusive=True, axis=-1)
            # Our padding mask is the inverse of these overflow locations.
            decoder_padding_mask = ~tf.cast(overflow, "bool")
        else:
            # Without early stopping, all locations will have been updated.
            decoder_padding_mask = tf.ones_like(decoder_token_ids, dtype="bool")

        return {
            "decoder_token_ids": decoder_token_ids,
            "decoder_padding_mask": decoder_padding_mask,
        }

    def _normalize_generate_inputs(
        self,
        inputs,
    ):
        """Normalizes user input to the generate function.

        This function converts all inputs to tensors, adds a batch dimension if
        necessary, and returns a iterable "dataset like" object (either an
        actual `tf.data.Dataset` or a list with a single batch element).
        """
        input_is_scalar = False

        if isinstance(inputs, tf.data.Dataset):
            return inputs, input_is_scalar

        def normalize(x):
            x_is_scalar = False
            if isinstance(x, str) or isinstance(x, list):
                x = tf.convert_to_tensor(x)

            if isinstance(x, tf.Tensor) and x.shape.rank == 0:
                x_is_scalar = True
                x = x[tf.newaxis]

            return x, x_is_scalar

        if isinstance(inputs, dict):
            for key in inputs:
                inputs[key], input_is_scalar = normalize(inputs[key])
        else:
            inputs, input_is_scalar = normalize(inputs)

        # We avoid converting to a dataset purely for speed, for a single batch
        # of input, creating a dataset would add significant overhead.
        return [inputs], input_is_scalar

    def _normalize_generate_outputs(
        self,
        outputs,
        input_is_scalar,
    ):
        """Normalizes user output from the generate function.

        This function converts the output to numpy (for integer output), or
        python strings (for string output). If a batch dimension was added to
        the input, it is removed from the output (so generate can be string in,
        string out).
        """

        def normalize(x):
            x = tf.concat(x, axis=0)
            x = tf.squeeze(x, 0) if input_is_scalar else x
            is_string = x.dtype == tf.string
            # Convert outputs to a friendly pythonic type. For numerical outputs
            # that is numpy, for string outputs that is `list` and `str`.
            return tensor_to_string_list(x) if is_string else x.numpy()

        if isinstance(outputs[0], dict):
            return {
                "decoder_token_ids": normalize(
                    [x["decoder_token_ids"] for x in outputs]
                ),
                "decoder_padding_mask": normalize(
                    [x["decoder_padding_mask"] for x in outputs]
                ),
            }
        return normalize([x for x in outputs])

    def generate(
        self,
        inputs,
        max_length=None,
    ):
        """Generates text conditioned on the encoder inputs.

        This method generates text based on given `inputs`. The sampling method
        used for generation can be set in the `compile` method.

        If `inputs` is a `tf.data.Dataset`, outputs will be generated
        "batch-by-batch" and concatenated. Otherwise, all inputs will be handled
        as a single batch.

        If a `preprocessor` is attached to the model, `inputs` can either be
        strings (encoder inputs), or a dictionary with `"encoder_text"` and
        `"decoder_text"` as keys and strings for values. The returned sequences
        will be strings. Otherwise, `inputs` should be preprocessed before
        calling `generate()` and the returned sequences will be token IDs.

        Args:
            inputs: a single input, batch of inputs, or `tf.data.Dataset` of
                batched inputs. If a preprocessor is attached, each input can be
                a simple string for basic conditional generation, or a
                dictionary with keys `"encoder_text"` and `"decoder_text"` to
                specify a prompt. If a preprocessor is not attached, input
                batches should have the same structure as when directly calling
                the model.
            max_length: int. The max length of generated sequence.
            add_start_token: bool. Whether to add the start token to `prompt`.
        """

        # Setup our three main passes.
        # 1. Optionally preprocessing strings to dense integer tensors.
        # 2. Generate new tokens via a compiled function on dense tensors.
        # 3. Optionally postprocess dense integer tensors back to string.
        generate_function = self.make_generate_function()
        end_token_id = None
        if self.preprocessor is not None:
            end_token_id = self.preprocessor.tokenizer.end_token_id

        def preprocess(x):
            return self.preprocessor.generate_preprocess(
                x, sequence_length=max_length
            )

        def generate(x):
            return generate_function(x, end_token_id=end_token_id)

        def postprocess(x):
            return self.preprocessor.generate_postprocess(x)

        # Normalize inputs, apply our three passes, and normalize outputs.
        inputs, input_is_scalar = self._normalize_generate_inputs(inputs)

        if self.preprocessor is not None:
            if isinstance(inputs, tf.data.Dataset):
                inputs = inputs.map(preprocess, tf.data.AUTOTUNE)
                inputs = inputs.prefetch(tf.data.AUTOTUNE)
            else:
                # Fast path for non-dataset, single-batch input.
                inputs = [preprocess(x) for x in inputs]

        outputs = [generate(x) for x in inputs]

        if self.preprocessor is not None:
            outputs = [postprocess(x) for x in outputs]

        return self._normalize_generate_outputs(outputs, input_is_scalar)
