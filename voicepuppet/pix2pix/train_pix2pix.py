#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import tensorflow as tf
import numpy as np
import os
from optparse import OptionParser
import logging
from pix2pix import Pix2PixNet
from generator.generator import Pix2PixDataGenerator
from utils.utils import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


if (__name__ == '__main__'):

  cmd_parser = OptionParser(usage="usage: %prog [options] --config_path <>")
  cmd_parser.add_option('--config_path', type="string", dest="config_path",
                        help='the config yaml file')

  opts, argv = cmd_parser.parse_args()

  if (opts.config_path is None):
    logger.error('Please check your parameters.')
    exit(0)

  config_path = opts.config_path

  if (not os.path.exists(config_path)):
    logger.error('config_path not exists')
    exit(0)

  os.environ["CUDA_VISIBLE_DEVICES"] = '0'

  batch_size = 16
  ### Generator for training setting
  train_generator = Pix2PixDataGenerator(config_path)
  params = train_generator.params
  params.dataset_path = params.train_dataset_path
  params.batch_size = batch_size
  train_generator.set_params(params)
  train_dataset = train_generator.get_dataset()

  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True
  sess = tf.Session(config=config)
  tf.train.start_queue_runners(sess=sess)

  train_iter = train_dataset.make_one_shot_iterator()

  ### Pix2PixNet setting
  pix2pixnet = Pix2PixNet(config_path)
  params = pix2pixnet.params
  epochs = params.training['epochs']
  params.add_hparam('max_to_keep', 2)
  params.add_hparam('save_dir', 'ckpt_pix2pixnet')
  params.add_hparam('save_name', 'pix2pixnet')
  params.add_hparam('save_step', 5000)
  params.add_hparam('summary_step', 100)
  params.add_hparam('eval_visual_dir', 'log/eval_pix2pixnet')
  params.add_hparam('summary_dir', 'log/summary_pix2pixnet')
  params.batch_size = batch_size
  pix2pixnet.set_params(params)

  mkdir(params.save_dir)
  mkdir(params.eval_visual_dir)
  mkdir(params.summary_dir)

  train_nodes = pix2pixnet.build_train_op(*train_iter.get_next())
  sess.run(tf.global_variables_initializer())

  # Restore from save_dir
  if ('checkpoint' in os.listdir(params.save_dir)):
    tf.train.Saver().restore(sess, tf.train.latest_checkpoint(params.save_dir))

  tf.summary.scalar("discriminator_loss", train_nodes['Discrim_loss'])
  tf.summary.scalar("generator_loss_GAN", train_nodes['Gen_loss_GAN'])
  tf.summary.scalar("generator_loss_L1", train_nodes['Gen_loss_L1'])

  with tf.name_scope("inputs_summary"):
    tf.summary.image("inputs", tf.image.convert_image_dtype(train_nodes['Inputs'][:,:,:,6:], dtype=tf.uint8))

  with tf.name_scope("targets_summary"):
    tf.summary.image("targets", tf.image.convert_image_dtype(train_nodes['Targets'][:,:,:,:], dtype=tf.uint8))

  with tf.name_scope("outputs_summary"):
    tf.summary.image("outputs", tf.image.convert_image_dtype(train_nodes['Outputs'][:,:,:,:], dtype=tf.uint8))

  # Add histograms for gradients.
  for grad, var in train_nodes['Discrim_grads_and_vars'] + train_nodes['Gen_grads_and_vars']:
    tf.summary.histogram(var.op.name + "/gradients", grad)

  merge_summary_op = tf.summary.merge_all()
  summary_writer = tf.summary.FileWriter(params.summary_dir, graph=sess.graph)

  for i in range(epochs):
    ### Run training
    result = sess.run([train_nodes['Train_op'],
                       merge_summary_op,
                       train_nodes['Gen_loss_GAN'],
                       train_nodes['Gen_loss_L1'],
                       train_nodes['Discrim_loss'],
                       train_nodes['Lr'],
                       train_nodes['Global_step']])
    _, summary, gen_loss_GAN, gen_loss_L1, discrim_loss, lr, global_step = result
    if(global_step % params.summary_step==0):
      print('Step {}, Lr= {:.2e}: \n\tgen_loss_GAN= {:.3f}, \n\tgen_loss_L1= {:.3f}, \n\tdiscrim_loss= {:.3f}'.format(global_step, lr, gen_loss_GAN, gen_loss_L1, discrim_loss))
      summary_writer.add_summary(summary, global_step)

    ### Save checkpoint
    if (global_step % params.save_step == 0):
      tf.train.Saver(max_to_keep=params.max_to_keep, var_list=tf.global_variables()).save(sess,
                                                                                          os.path.join(params.save_dir,
                                                                                                       params.save_name),
                                                                                          global_step=global_step)