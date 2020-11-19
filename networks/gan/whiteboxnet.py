import torch.nn as nn
from torch.nn.utils import spectral_norm
from networks.commons import Mean
from networks import NETWORKS

def calc(pad, h, k, s):
  import math
  return math.floor((h + 2 * pad - (k - 1) - 1) / s + 1)


class ResBlock(nn.Module):
  def __init__(self, in_channel, out_channel=32):
    super().__init__()
    self.conv = nn.Conv2d(in_channel, out_channel, [3, 3], padding=1)
    self.conv1 = nn.Conv2d(out_channel, out_channel, [3, 3], padding=1)
    self.leaky_relu = nn.LeakyReLU(inplace=True)

  def forward(self, inputs):
    x = self.conv1(self.leaky_relu(self.conv1(inputs)))
    return x + inputs

@NETWORKS.register()
class UnetGenerator(nn.Module):
  def __init__(self, channel=32, num_blocks=4):
    super().__init__()

    self.conv = nn.Conv2d(3, channel, [7, 7], padding=3)  # same 256,256
    self.conv1 = nn.Conv2d(channel, channel, [3, 3], stride=2, padding=1)  # same 128,128
    self.conv2 = nn.Conv2d(channel, channel * 2, [3, 3], padding=1)  # 128,128
    self.conv3 = nn.Conv2d(channel * 2, channel * 2, [3, 3], stride=2, padding=1)  # 64,64
    self.conv4 = nn.Conv2d(channel * 2, channel * 4, [3, 3], padding=1)  # 64,64

    self.resblock = nn.Sequential(*[ResBlock(channel * 4, channel * 4) for i in range(num_blocks)])

    self.conv5 = nn.Conv2d(channel * 4, channel * 2, [3, 3], padding=1)  # 64,64
    self.conv6 = nn.Conv2d(channel * 2, channel * 2, [3, 3], padding=1)  # 64,64
    self.conv7 = nn.Conv2d(channel * 2, channel, [3, 3], padding=1)  # 64,64
    self.conv8 = nn.Conv2d(channel, channel, [3, 3], padding=1)  # 64,64
    self.conv9 = nn.Conv2d(channel, 3, [7, 7], padding=3)  # 64,64

    self.leak_relu = nn.LeakyReLU(inplace=True)
    self.upsample = nn.UpsamplingBilinear2d(scale_factor=2)
    self.act = nn.Tanh()

  def forward(self, inputs):
    x0 = self.conv(inputs)
    x0 = self.leak_relu(x0)  # 256, 256, 32

    x1 = self.conv1(x0)
    x1 = self.leak_relu(x1)
    x1 = self.conv2(x1)
    x1 = self.leak_relu(x1)  # 128, 128, 64

    x2 = self.conv3(x1)
    x2 = self.leak_relu(x2)
    x2 = self.conv4(x2)
    x2 = self.leak_relu(x2)  # 64, 64, 128

    x2 = self.resblock(x2)  # 64, 64, 128
    x2 = self.conv5(x2)
    x2 = self.leak_relu(x2)  # 64, 64, 64

    x3 = self.upsample(x2)
    x3 = self.conv6(x3 + x1)
    x3 = self.leak_relu(x3)
    x3 = self.conv7(x3)
    x3 = self.leak_relu(x3)  # 128, 128, 32

    x4 = self.upsample(x3)
    x4 = self.conv8(x4 + x0)
    x4 = self.leak_relu(x4)
    x4 = self.conv9(x4)  # 256, 256, 32

    return self.act(x4)

@NETWORKS.register()
class SpectNormDiscriminator(nn.Module):
  """SpectNormDiscriminator
  ----------------------------------------------------------------
          Layer (type)               Output Shape         Param #
  ================================================================
              Conv2d-1         [-1, 32, 128, 128]             896
          LeakyReLU-2         [-1, 32, 128, 128]               0
              Conv2d-3         [-1, 32, 128, 128]           9,248
          LeakyReLU-4         [-1, 32, 128, 128]               0
              Conv2d-5           [-1, 64, 64, 64]          18,496
          LeakyReLU-6           [-1, 64, 64, 64]               0
              Conv2d-7           [-1, 64, 64, 64]          36,928
          LeakyReLU-8           [-1, 64, 64, 64]               0
              Conv2d-9          [-1, 128, 32, 32]          73,856
          LeakyReLU-10          [-1, 128, 32, 32]               0
            Conv2d-11          [-1, 128, 32, 32]         147,584
          LeakyReLU-12          [-1, 128, 32, 32]               0
            Conv2d-13            [-1, 1, 32, 32]             129
  ================================================================
  Total params: 287,137
  Trainable params: 287,137
  Non-trainable params: 0
  """  
  def __init__(self, channel=32, patch=True):
    super().__init__()
    self.channel = channel
    self.patch = patch
    in_channel = 3
    l = []
    for idx in range(3):
      l.extend([
          spectral_norm(nn.Conv2d(in_channel, channel * (2**idx), 3, stride=2, padding=1)),
          nn.LeakyReLU(inplace=True),
          spectral_norm(nn.Conv2d(channel * (2**idx), channel * (2**idx), 3, stride=1, padding=1)),
          nn.LeakyReLU(inplace=True),
      ])
      in_channel = channel * (2**idx)
    self.body = nn.Sequential(*l)
    if self.patch:
      self.head = spectral_norm(nn.Conv2d(in_channel, 1, 1, padding=0))
    else:
      self.head = nn.Sequential(Mean([1, 2]), nn.Linear(in_channel, 1))

  def forward(self, x):
    x = self.body(x)
    x = self.head(x)
    return x
