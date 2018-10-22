"""
    MENet, implemented in TensorFlow.
    Original paper: 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile Applications,'
    https://arxiv.org/abs/1803.09127.
"""

__all__ = ['menet', 'menet108_8x1_g3', 'menet128_8x1_g4', 'menet160_8x1_g8', 'menet228_12x1_g3', 'menet256_12x1_g4',
           'menet348_12x1_g3', 'menet352_12x1_g8', 'menet456_24x1_g3']

import os
import tensorflow as tf
from .common import conv2d, conv1x1, batchnorm, channel_shuffle, maxpool2d, avgpool2d


def depthwise_conv3x3(x,
                      channels,
                      strides,
                      name="depthwise_conv3x3"):
    """
    Depthwise convolution 3x3 layer. This is exactly the same layer as in ShuffleNet.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    channels : int
        Number of input/output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    name : str, default 'depthwise_conv3x3'
        Block name.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    return conv2d(
        x=x,
        in_channels=channels,
        out_channels=channels,
        kernel_size=3,
        strides=strides,
        padding=1,
        groups=channels,
        use_bias=False,
        name=name)


def group_conv1x1(x,
                  in_channels,
                  out_channels,
                  groups,
                  name="group_conv1x1"):
    """
    Group convolution 1x1 layer. This is exactly the same layer as in ShuffleNet.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    groups : int
        Number of groups.
    name : str, default 'depthwise_conv3x3'
        Block name.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    return conv2d(
        x=x,
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=1,
        groups=groups,
        use_bias=False,
        name=name)


def conv3x3(x,
            in_channels,
            out_channels,
            strides,
            name="conv3x3"):
    """
    Convolution 3x3 layer.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    name : str, default 'conv3x3'
        Block name.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    return conv2d(
        x=x,
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=3,
        strides=strides,
        padding=1,
        use_bias=False,
        name=name)


def me_unit(x,
            in_channels,
            out_channels,
            side_channels,
            groups,
            downsample,
            ignore_group,
            training,
            name="me_unit"):
    """
    MENet unit.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    side_channels : int
        Number of side channels.
    groups : int
        Number of groups in convolution layers.
    downsample : bool
        Whether do downsample.
    ignore_group : bool
        Whether ignore group value in the first convolution layer.
    training : bool, or a TensorFlow boolean scalar tensor, default False
      Whether to return the output in training mode or in inference mode.
    name : str, default 'me_unit'
        Unit name.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    mid_channels = out_channels // 4

    if downsample:
        out_channels -= in_channels

    # identity = tf.identity(x)
    identity = x

    # pointwise group convolution 1
    x = group_conv1x1(
        x=x,
        in_channels=in_channels,
        out_channels=mid_channels,
        groups=(1 if ignore_group else groups),
        name=name + "/compress_conv1")
    x = batchnorm(
        x=x,
        training=training,
        name=name + "/compress_bn1")
    x = tf.nn.relu(x, name=name + "/compress_activ")

    assert (mid_channels % groups == 0)
    x = channel_shuffle(
        x=x,
        groups=groups)

    # merging
    y = conv1x1(
        x=x,
        in_channels=mid_channels,
        out_channels=side_channels,
        name=name + "/s_merge_conv")
    y = batchnorm(
        x=y,
        training=training,
        name=name + "/s_merge_bn")
    y = tf.nn.relu(y, name=name + "/s_merge_activ")

    # depthwise convolution (bottleneck)
    x = depthwise_conv3x3(
        x=x,
        channels=mid_channels,
        strides=(2 if downsample else 1),
        name=name + "/dw_conv2")
    x = batchnorm(
        x=x,
        training=training,
        name=name + "/dw_bn2")

    # evolution
    y = conv3x3(
        x=y,
        in_channels=side_channels,
        out_channels=side_channels,
        strides=(2 if downsample else 1),
        name=name + "/s_conv")
    y = batchnorm(
        x=y,
        training=training,
        name=name + "/s_conv_bn")
    y = tf.nn.relu(y, name=name + "/s_conv_activ")

    y = conv1x1(
        x=y,
        in_channels=side_channels,
        out_channels=mid_channels,
        name=name + "/s_evolve_conv")
    y = batchnorm(
        x=y,
        training=training,
        name=name + "/s_evolve_bn")
    y = tf.nn.sigmoid(y, name=name + "/s_evolve_activ")

    x = x * y
    # x = tf.multiply(x, y, name=name + "/mul")

    # pointwise group convolution 2
    x = group_conv1x1(
        x=x,
        in_channels=mid_channels,
        out_channels=out_channels,
        groups=groups,
        name=name + "/expand_conv3")
    x = batchnorm(
        x=x,
        training=training,
        name=name + "/expand_bn3")

    if downsample:
        identity = avgpool2d(
            x=identity,
            pool_size=3,
            strides=2,
            padding=1,
            name=name + "/avgpool")
        # identity = tf.layers.average_pooling2d(
        #     inputs=identity,
        #     pool_size=3,
        #     strides=2,
        #     padding='same',
        #     data_format='channels_first',
        #     name=name + "/avgpool")
        x = tf.concat([x, identity], axis=1, name=name + "/concat")
    else:
        x = x + identity

    x = tf.nn.relu(x, name=name + "/final_activ")
    return x


def me_init_block(x,
                  in_channels,
                  out_channels,
                  training,
                  name="me_init_block"):
    """
    MENet specific initial block.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    training : bool, or a TensorFlow boolean scalar tensor, default False
      Whether to return the output in training mode or in inference mode.
    name : str, default 'shuffle_init_block'
        Block name.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    x = conv2d(
        x=x,
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=3,
        strides=2,
        padding=1,
        use_bias=False,
        name=name + "/conv")
    x = batchnorm(
        x=x,
        training=training,
        name=name + "/bn")
    x = tf.nn.relu(x, name=name + "/activ")
    x = maxpool2d(
        x=x,
        pool_size=3,
        strides=2,
        padding=1,
        name=name + "/pool")
    return x


def menet(x,
          channels,
          init_block_channels,
          side_channels,
          groups,
          in_channels=3,
          classes=1000,
          training=False):
    """
    ShuffleNet model from 'ShuffleNet: An Extremely Efficient Convolutional Neural Network for Mobile Devices,'
    https://arxiv.org/abs/1707.01083.

    Parameters:
    ----------
    x : Tensor
        Input tensor.
    channels : list of list of int
        Number of output channels for each unit.
    init_block_channels : int
        Number of output channels for the initial unit.
    side_channels : int
        Number of side channels in a ME-unit.
    groups : int
        Number of groups in convolution layers.
    in_channels : int, default 3
        Number of input channels.
    classes : int, default 1000
        Number of classification classes.
    training : bool, or a TensorFlow boolean scalar tensor, default False
      Whether to return the output in training mode or in inference mode.

    Returns
    -------
    Tensor
        Resulted tensor.
    """
    x = me_init_block(
        x=x,
        in_channels=in_channels,
        out_channels=init_block_channels,
        training=training,
        name="features/init_block")
    in_channels = init_block_channels
    for i, channels_per_stage in enumerate(channels):
        for j, out_channels in enumerate(channels_per_stage):
            downsample = (j == 0)
            ignore_group = (i == 0) and (j == 0)
            x = me_unit(
                x=x,
                in_channels=in_channels,
                out_channels=out_channels,
                side_channels=side_channels,
                groups=groups,
                downsample=downsample,
                ignore_group=ignore_group,
                training=training,
                name="features/stage{}/unit{}".format(i + 1, j + 1))
            in_channels = out_channels
    x = tf.layers.average_pooling2d(
        inputs=x,
        pool_size=7,
        strides=1,
        data_format='channels_first',
        name="features/final_pool")

    x = tf.layers.flatten(x)
    x = tf.layers.dense(
        inputs=x,
        units=classes,
        name="output")

    return x


def get_menet(first_stage_channels,
              side_channels,
              groups,
              model_name=None,
              pretrained=False,
              root=os.path.join('~', '.tensorflow', 'models'),
              **kwargs):
    """
    Create MENet model with specific parameters.

    Parameters:
    ----------
    first_stage_channels : int
        Number of output channels at the first stage.
    side_channels : int
        Number of side channels in a ME-unit.
    groups : int
        Number of groups in convolution layers.
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """

    layers = [4, 8, 4]

    if first_stage_channels == 108:
        init_block_channels = 12
        channels_per_layers = [108, 216, 432]
    elif first_stage_channels == 128:
        init_block_channels = 12
        channels_per_layers = [128, 256, 512]
    elif first_stage_channels == 160:
        init_block_channels = 16
        channels_per_layers = [160, 320, 640]
    elif first_stage_channels == 228:
        init_block_channels = 24
        channels_per_layers = [228, 456, 912]
    elif first_stage_channels == 256:
        init_block_channels = 24
        channels_per_layers = [256, 512, 1024]
    elif first_stage_channels == 348:
        init_block_channels = 24
        channels_per_layers = [348, 696, 1392]
    elif first_stage_channels == 352:
        init_block_channels = 24
        channels_per_layers = [352, 704, 1408]
    elif first_stage_channels == 456:
        init_block_channels = 48
        channels_per_layers = [456, 912, 1824]
    else:
        raise ValueError("The {} of `first_stage_channels` is not supported".format(first_stage_channels))

    channels = [[ci] * li for (ci, li) in zip(channels_per_layers, layers)]

    def net_lambda(x,
                   training=False,
                   channels=channels,
                   init_block_channels=init_block_channels,
                   side_channels=side_channels,
                   groups=groups):
        y_net = menet(
            x=x,
            channels=channels,
            init_block_channels=init_block_channels,
            side_channels=side_channels,
            groups=groups,
            training=training,
            **kwargs)
        return y_net

    if pretrained:
        if (model_name is None) or (not model_name):
            raise ValueError("Parameter `model_name` should be properly initialized for loading pretrained model.")
        from .model_store import get_model_file
        net_file_path = get_model_file(
            model_name=model_name,
            local_model_store_dir_path=root)
    else:
        net_file_path = None

    return net_lambda, net_file_path


def menet108_8x1_g3(**kwargs):
    """
    108-MENet-8x1 (g=3) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=108, side_channels=8, groups=3, model_name="menet108_8x1_g3", **kwargs)


def menet128_8x1_g4(**kwargs):
    """
    128-MENet-8x1 (g=4) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=128, side_channels=8, groups=4, model_name="menet128_8x1_g4", **kwargs)


def menet160_8x1_g8(**kwargs):
    """
    160-MENet-8x1 (g=8) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=160, side_channels=8, groups=8, model_name="menet160_8x1_g8", **kwargs)


def menet228_12x1_g3(**kwargs):
    """
    228-MENet-12x1 (g=3) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=228, side_channels=12, groups=3, model_name="menet228_12x1_g3", **kwargs)


def menet256_12x1_g4(**kwargs):
    """
    256-MENet-12x1 (g=4) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=256, side_channels=12, groups=4, model_name="menet256_12x1_g4", **kwargs)


def menet348_12x1_g3(**kwargs):
    """
    348-MENet-12x1 (g=3) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=348, side_channels=12, groups=3, model_name="menet348_12x1_g3", **kwargs)


def menet352_12x1_g8(**kwargs):
    """
    352-MENet-12x1 (g=8) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=352, side_channels=12, groups=8, model_name="menet352_12x1_g8", **kwargs)


def menet456_24x1_g3(**kwargs):
    """
    456-MENet-24x1 (g=3) model from 'Merging and Evolution: Improving Convolutional Neural Networks for Mobile
    Applications,' https://arxiv.org/abs/1803.09127.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.tensorflow/models'
        Location for keeping the model parameters.

    Returns
    -------
    net_lambda : function
        Function for model graph creation.
    net_file_path : str or None
        File path for pretrained model or None.
    """
    return get_menet(first_stage_channels=456, side_channels=24, groups=3, model_name="menet456_24x1_g3", **kwargs)


def _test():
    import numpy as np
    from .model_store import load_model

    pretrained = False

    models = [
        menet108_8x1_g3,
        menet128_8x1_g4,
        menet160_8x1_g8,
        menet228_12x1_g3,
        menet256_12x1_g4,
        menet348_12x1_g3,
        menet352_12x1_g8,
        menet456_24x1_g3,
    ]

    for model in models:

        net_lambda, net_file_path = model(pretrained=pretrained)

        x = tf.placeholder(
            dtype=tf.float32,
            shape=(None, 3, 224, 224),
            name='xx')
        y_net = net_lambda(x)

        weight_count = np.sum([np.prod(v.get_shape().as_list()) for v in tf.trainable_variables()])
        print("m={}, {}".format(model.__name__, weight_count))
        assert (model != menet108_8x1_g3 or weight_count == 654516)
        assert (model != menet128_8x1_g4 or weight_count == 750796)
        assert (model != menet160_8x1_g8 or weight_count == 850120)
        assert (model != menet228_12x1_g3 or weight_count == 1806568)
        assert (model != menet256_12x1_g4 or weight_count == 1888240)
        assert (model != menet348_12x1_g3 or weight_count == 3368128)
        assert (model != menet352_12x1_g8 or weight_count == 2272872)
        assert (model != menet456_24x1_g3 or weight_count == 5304784)

        with tf.Session() as sess:
            if pretrained:
                load_model(sess=sess, file_path=net_file_path)
            else:
                sess.run(tf.global_variables_initializer())
            x_value = np.zeros((1, 3, 224, 224), np.float32)
            y = sess.run(y_net, feed_dict={x: x_value})
            assert (y.shape == (1, 1000))
        tf.reset_default_graph()


if __name__ == "__main__":
    _test()