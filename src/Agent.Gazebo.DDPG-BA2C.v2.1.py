# # Reinforcement Learning : DDPG-A2C : actor output scaled with boundary + target network + separated network + random + dueling critic network
## We wish to guarantee some policy improvements little by little.

## TODO : implement the target network trick ?
useGAZEBO = False
fromState = True
equilibriumBased = True
coupledSystem = False
strongCoupling = False
NLonly = False
if NLonly :
	coupledSystem = True
	
freqSkipFrame = 1000


show = False
#load_model = True
load_model = False
energy_based = True
#base_port = 11320
#base_port = 11311
#base_port = 11411
base_port = 11452
if NLonly :
	base_port = 11330 #NLonly
reward_bound = 1e1

import threading
import multiprocessing
import numpy as np
import time
import timeit
import random

if useGAZEBO :
	from GazeboRL import GazeboRL, Swarm1GazeboRL, init_roscore
	import rospy
	from Agent1 import NN, INPUT_SHAPE_R, resize, rgb2yuv
	from cv_bridge import CvBridge
	bridge = CvBridge()

	def ros2np(img) :
		return bridge.imgmsg_to_cv2(img, "bgr8")
else :
	import gym

import cv2
import os
import numpy as np
from replayBuffer import EXP, PER
alphaPER = 0.7


if useGAZEBO :
	nbrinput = INPUT_SHAPE_R
	nbroutput = 2
	filepath_base = './logs/'
	#dropoutK = 0.5
	dropoutK=1.0
	batch_size = 1024 
	lr = 5.0e-4
	def initAgent():		
		model = NN( filepath_base,nbrinput=nbrinput,nbroutput=nbroutput,lr=lr,filepathin=None)
		model.init()
		return model
	


if useGAZEBO :
	env= list()
	env.append( Swarm1GazeboRL(base_port,energy_based, coupledSystem=coupledSystem, fromState=fromState, equilibriumBased=equilibriumBased) )
	base_port += 1
	env[0].make()
	print('\n\nwait for 5 sec...\n\n')
	time.sleep(5)
	env[0].reset()
	env[0].setPause(False)
	#LoopRate = rospy.Rate(60)

nbrskipframe = 1
if useGAZEBO :
	#img_size = (180,320,3)
	#img_size = (90,80,nbrskipframe)
	#img_size = (120,320,nbrskipframe)
	nbrskipframe = 4
	#img_size = (120,160,nbrskipframe)
	img_size = (120,120,nbrskipframe)
	if fromState :
		img_size= (1,5,nbrskipframe)
else :
	nbrskipframe = 1
	img_size = (84,84,nbrskipframe)
	#img_size = (3,1,nbrskipframe)#(84,84,nbrskipframe)
						

rec = False
# In[35]:

a_bound = 1.0

if useGAZEBO:
	if coupledSystem :
		a_bound = 2.0
else :
	a_bound = 2.0
		
if fromState :
	maxReplayBufferSize = 200000#100000#2500
	max_episode_length = 2000
else :
	maxReplayBufferSize = 10000#2500
	max_episode_length = 800


updateT = 1e-0

#updateTauTarget = 1e-6
#updateTauTarget = 1e-5
#updateTauTarget = 5e-5
#updateTauTarget = 1e-4
#updateTauTarget = 1e-4
#updateTauTarget = 5e-4
updateTauTarget = 1e-3
#updateTauTarget = 1e-1


#nbrStepsPerReplay = 16
#nbrStepsPerReplay = 32
if useGAZEBO :
	nbrStepsPerReplay = 4#32
	if fromState :
		nbrStepsPerReplay = 32
else :
	nbrStepsPerReplay = 64
#nbrStepsPerReplay = 128


gamma = 0.99 # discount rate for advantage estimation and reward discounting
imagesize = [img_size[0],img_size[1], img_size[2] ]
s_size = imagesize[0]*imagesize[1]*imagesize[2]

if useGAZEBO == False :
	nbrskipframe = 1
	s_size = nbrskipframe*3
	
h_size = 256

a_size = 1
eps_greedy_prob = 0.3
		
num_workers = 8
if NLonly :
	num_workers = 1
threadExploration = False

lr=1e-4
#lr=5e-4
#lr=1e-3

dividerNoise = 100.0#2.0

if useGAZEBO :
	a_size = 2	
	model_path = './DDPG-BA2C-r1s-'+'w'+str(num_workers)+'-divNoise'+str(dividerNoise)+'-lr'+str(lr)+'-b'+str(nbrStepsPerReplay)+'-T'+str(updateT)+'-tau'+str(updateTauTarget)+'-skip'+str(nbrskipframe)
	if threadExploration :
		model_path = model_path+'+TheadExploration'
	if fromState :
		model_path = './FromState/'+model_path
	if coupledSystem :
		model_path = model_path+'+coupledSystem'
	if strongCoupling :
		model_path = model_path+'+strongCoupling'
	if equilibriumBased :
		model_path = model_path+'+equilibriumBased'
	if NLonly :
		model_path = './NLonly/'+model_path
		
else :	
	model_path = './DDPG-BA2C-v2+PER-alpha'+str(alphaPER)+'-w'+str(num_workers)+'-divNoise'+str(dividerNoise)+'-lr'+str(lr)+'-b'+str(nbrStepsPerReplay)+'-T'+str(updateT)+'-tau'+str(updateTauTarget)+'-skip'+str(nbrskipframe)



if not os.path.exists(model_path):
    os.makedirs(model_path)    
#Create a directory to save episode playback gifs to
if not os.path.exists('./frames'):
    os.makedirs('./frames')



def preprocess(image, imghr=60, imgwr=320) :
	img = resize(image, imghr, imgwr)
	image = rgb2yuv(img)
	image = np.mean( image, axis=2)
	image = np.array(image)*1.0/127.5
	image -= 1.0
	#plt.imshow(image)
	#plt.show()
	return image.reshape((1,-1,1))
	
def envstep(env,action) :
	outimg = None
	outcmd = None
	outr = None
	outdone = False
	outinfo = None
	
	output = env.step(action)
	while output[0] is None :
		output = env.step(action)
	
	if output[0] is not None :
		for topic in output[0].keys() :
			#rospy.loginfo(topic)
			if 'OMNIVIEW' in topic :
				img = np.array(ros2np(output[0][topic]))
				shape = img.shape
				outimg = img.reshape( (shape[0],shape[1],shape[2], 1) )
				
			if 'controlLaw' in topic :
				twist = output[0][topic]
				#rospy.loginfo('twist : {}'.format(twist) )
				outcmd = np.array( [twist.linear.x, twist.angular.z]).reshape((1,2,1) )
	else :
		outimg = np.zeros(shape=img_size)
		outcmd = np.zeros(shape=(1,a_size))
	
	if output[1] is not None :
		outr = output[1]['/RL/reward'].data
	
	if output[2] is not None :
		outdone = output[2]
		
	if output[3] is not None :
		outinfo = output[3]
	
	return (outimg, outcmd), outr, outdone, outinfo
	
def envstepstate(env,action) :
	outstate = None
	outcmd = None
	outr = None
	outdone = False
	outinfo = None
	
	output = env.step(action)
	while output[0] is None :
		output = env.step(action)
	
	
	if output[0] is not None :
		for topic in output[0].keys() :
			#rospy.loginfo(topic)
			if 'state' in topic :
				#let us collect relevant data :
				values = output[0][topic]
				r = values.data[0]
				theta = values.data[1]
				phi = values.data[2]
				robs = values.data[3]
				thetaobs = values.data[4]
				#let us fill in the return value :
				outstate = np.array([r, theta, phi, robs, thetaobs]).reshape((1,s_size/nbrskipframe, 1))
			if 'controlLaw' in topic :
				twist = output[0][topic]
				#rospy.loginfo('twist : {}'.format(twist) )
				outcmd = np.array( [twist.linear.x, twist.angular.z]).reshape( (1,2,1) )
	else :
		outstate = np.zeros(shape=(1,s_size/nbrskipframe,1))
		outcmd = np.zeros(shape=(1,a_size))
	
	if output[1] is not None :
		outr = output[1]['/RL/reward'].data
	
	if output[2] is not None :
		outdone = output[2]
		
	if output[3] is not None :
		outinfo = output[3]
		
	return (outstate,outcmd), outr, outdone, outinfo
	
	
def envstep(env,action,fromState) :
	outputs = list()
	looprate = rospy.Rate(freqSkipFrame)
	
	for i in range(nbrskipframe) :
		if fromState == False :
			outputs.append( envstep(env,action) )
		else :
		 	outputs.append( envstepstate(env,action) )
		looprate.sleep()
	
	#for el in outputs :
	#	rospy.loginfo(el)
	#rospy.loginfo('--------------')
		
	if fromState :
		obs = np.concatenate( [ outputs[i][0][0] for i in range(nbrskipframe) ], axis=2 )
	else :
		obs = np.concatenate( [ outputs[i][0][0] for i in range(nbrskipframe) ], axis=3 )
	#rospy.loginfo('OBS : {}'.format(obs.shape) )
	if outputs[0][0][1] is not None :
		cmd = np.concatenate( [ outputs[i][0][1] for i in range(nbrskipframe) ], axis=2 )
	else :
		cmd = None
	
	outr = np.mean( [ outputs[i][1] for i in range(nbrskipframe) ] )
	outdone = outputs[-1][2]
	outinfo = outputs[-1][3]
	
	return (obs,cmd), outr, outdone, outinfo


import sys, traceback,logging
import tensorflow as tf
import tensorflow.contrib.slim as slim
#get_ipython().magic('matplotlib inline')

from random import choice
from time import sleep
from time import time

# In[20]:

# Copies one set of variables to another.
# Used to set worker network parameters to those of global network.
def update_target_graph(from_scope,to_scope,updateTau=1e-3):
	from_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, from_scope)
	to_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, to_scope)
	print('UPDATE {} towards {} with tau = {}'.format(to_scope,from_scope,updateTau) )
	op_holder = []
	for from_var,to_var in zip(from_vars,to_vars):
		op_holder.append(to_var.assign( tf.multiply(updateTau,from_var)+tf.multiply( (1.0-updateTau), to_var) ))
	return op_holder

def update_thread_graph(from_scope,to_scope,updateTau=1e0):
	from_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, from_scope)
	to_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, to_scope)
	print('UPDATE {} towards {} with tau = {}'.format(to_scope,from_scope,updateTau) )
	op_holder = []
	for from_var,to_var in zip(from_vars,to_vars):
		op_holder.append(to_var.assign( tf.multiply(updateTau,from_var)+tf.multiply( (1.0-updateTau), to_var) ))
	return op_holder



# NEED :
# 1- update each thread target network to base target network with tau=1
# 2- update each thread network to base network with tau=1
# 3- update the base target network towards the base master network with tau=updateTau=1e-3




# Processes Doom screen image to produce cropped and resized image. 
def process_frame(frame):
	#s = frame[10:-10,30:-30]
	s = scipy.misc.imresize(s,[84,84])
	s = np.reshape(s,[np.prod(s.shape)]) / 255.0
	return s

# Discounting function used to calculate discounted returns.
def discount(x, gamma):
    return scipy.signal.lfilter([1], [1, -gamma], x[::-1], axis=0)[::-1]

#Used to initialize weights for policy and value output layers
def normalized_columns_initializer(std=1.0):
    def _initializer(shape, dtype=None, partition_info=None):
        out = np.random.randn(*shape).astype(np.float32)
        out *= std / np.sqrt(np.square(out).sum(axis=0, keepdims=True))
        return tf.constant(out)
    return _initializer

def BNlayer(x, is_training, scope):
   bn_train = tf.contrib.layers.batch_norm(x, decay=0.999, center=True, scale=True, updates_collections=None, is_training=True, scope=scope)
   bn_inference = tf.contrib.layers.batch_norm(x, decay=0.999, center=True, scale=True, updates_collections=None, is_training=False, scope=scope, reuse=True)
   bn = tf.cond(is_training, lambda: bn_train, lambda: bn_inference)
   return bn

# In[21]:

class AC_Network():
	def __init__(self,imagesize,s_size,h_size, a_size,a_bound,scope,trainer,tau=1e-2,rec=False,dropoutK=1.0,useGAZEBO=False, fromState=False, strongCoupling=False):
		self.useGAZEBO = useGAZEBO
		self.fromState = fromState
		self.strongCoupling = strongCoupling
		
		self.imagesize = imagesize
		self.nbrskipframe = imagesize[2]
		self.s_size = s_size
		self.h_size = h_size
		self.a_size = a_size
		self.a_bound = a_bound
		self.scope = scope
		self.trainer = trainer
		self.tau = tau
		self.rec = rec
		self.dropoutK = dropoutK
		self.nbrOutput = 128
		
		self.l2_loss = tf.constant(0.0)
		self.lambda_regL2 = 0.0	
		
		self.summary_ops = []
		
		#inputs, actions, policy, Vvalue, Qvalue, keep_prob, phase
		self.inputs, self.actions, self.cmd, self.policy, self.Vvalue, self.Qvalue, self.keep_prob, self.phase = self.create_network(self.scope)
		self.t_inputs, self.t_actions, self.t_cmd, self.t_policy, self.t_Vvalue, self.t_Qvalue, self.t_keep_prob, self.t_phase = self.create_network(self.scope+'_target')
		
		self.build_loss_functions()
		
		self.summary_ops = tf.summary.merge( self.summary_ops )
		 
	
	
	def weight_variable(self,shape, name=None,std=None, uniform=False):
		#initial = tf.Variable(tf.truncated_normal(shape, stddev=1.0/np.sqrt(shape[0])))
		scale = 1.0/np.sqrt(shape[0])
		if std is not None :
			scale = std
		if uniform :
			initial = tf.Variable(tf.random_uniform(shape, minval=-scale,maxval=scale,dtype=tf.float32, name=name) )
		else :
			initial = tf.Variable(tf.truncated_normal(shape, stddev=scale,dtype=tf.float32, name=name) )
		self.l2_loss += tf.nn.l2_loss(initial)
		return initial

	def bias_variable(self,shape):
		#initial = tf.constant(1e-4, shape=shape)
		initial = tf.Variable(tf.truncated_normal(shape, stddev=1.0/np.sqrt(shape[0])) )
		return initial

	def variable_summaries(self,var, name):
		  """Attach a lot of summaries to a Tensor."""
		  with tf.name_scope('summaries'):
		      #mean = tf.reduce_mean(var)
		      #self.summary_ops.append( tf.summary.scalar('mean/' + name, mean) )
		      #with tf.name_scope('stddev'):
		      #    stddev = tf.sqrt(tf.reduce_mean(tf.square(var - mean)))
		      #self.summary_ops.append( tf.summary.scalar('stddev/' + name, stddev) )
		      #self.summary_ops.append( tf.summary.scalar('max/' + name, tf.reduce_max(var)) )
		      #self.summary_ops.append( tf.summary.scalar('min/' + name, tf.reduce_min(var)) )
		      self.summary_ops.append( tf.summary.histogram(name, var) )

	def nn_layer(self,input_tensor, input_dim, output_dim, layer_name, act=tf.nn.relu, std=None, uniform=False):
		"""Reusable code for making a simple neural net layer.
		It does a matrix multiply, bias add, and then uses relu to nonlinearize.
		It also sets up name scoping so that the resultant graph is easy to read,
		and adds a number of summary ops.
		"""
		# Adding a name scope ensures logical grouping of the layers in the graph.
		with tf.name_scope(layer_name):
			# This Variable will hold the state of the weights for the layer
			with tf.name_scope('weights'):
				weights = self.weight_variable([input_dim, output_dim], std=std)
				self.variable_summaries(weights, layer_name + '/weights')
			with tf.name_scope('biases'):
				biases = self.bias_variable([output_dim])
				self.variable_summaries(biases, layer_name + '/biases')
			with tf.name_scope('Wx_plus_b'):
				preactivate = tf.matmul(input_tensor, weights) + biases
				tf.summary.histogram(layer_name + '/pre_activations', preactivate)
			activations = act(preactivate, name='activation')
			self.summary_ops.append( tf.summary.histogram(layer_name + '/activations', activations) )
			
			print("layer : "+layer_name+"/fc : input : batch x {} // batch x {}".format(input_dim,output_dim))
			
			return activations
	
	def nn_layerBN(self,input_tensor, input_dim, output_dim, phase, layer_name, act=tf.nn.relu, std=None, uniform=False):
		"""Reusable code for making a simple neural net layer.
		It does a matrix multiply, bias add, and then uses relu to nonlinearize.
		It also sets up name scoping so that the resultant graph is easy to read,
		and adds a number of summary ops.
		"""
		# Adding a name scope ensures logical grouping of the layers in the graph.
		with tf.name_scope(layer_name):
			# This Variable will hold the state of the weights for the layer
			with tf.name_scope('weights'):
				weights = self.weight_variable([input_dim, output_dim], std=std)
				self.variable_summaries(weights, layer_name + '/weights')
			with tf.name_scope('biases'):
				biases = self.bias_variable([output_dim])
				self.variable_summaries(biases, layer_name + '/biases')
			with tf.name_scope('Wx_plus_b'):
				preactivate = tf.matmul(input_tensor, weights) + biases
				#preactivate = tf.contrib.layers.batch_norm(preactivate, center=True, scale=True, reuse=True, is_training=phase,scope=layer_name+'/bn')
				preactivate = BNlayer(preactivate, is_training=phase, scope=layer_name+'/bn')
				self.summary_ops.append( tf.summary.histogram(layer_name + '/pre_activations', preactivate) )
			activations = act(preactivate, name='activation')
			self.summary_ops.append( tf.summary.histogram(layer_name + '/activations', activations) )
			
			print("layer : "+layer_name+"/fc_BN : input : batch x {} // batch x {}".format(input_dim,output_dim))
			
			return activations
		
	def layer_conv2dBNAct(self,input_tensor, input_dim, output_dim, phase, layer_name='conv2dBNAct', act=tf.identity, filter_size=3, stride=1, padding='SAME', uniform=False):
		"""Reusable code for making a conv-BN-act neural net layer that give the same size output with default parameters.
		
		It does a conv, add biases,batch normalize and then uses relu to nonlinearize.
		It also sets up name scoping so that the resultant graph is easy to read,
		and adds a number of summary ops.
		"""
		# Adding a name scope ensures logical grouping of the layers in the graph.
		with tf.name_scope(layer_name):
			
			# Variable handling :
			with tf.name_scope('weights'):
				weights = self.weight_variable([filter_size, filter_size, input_dim[3], output_dim[0]])
				self.variable_summaries(weights, layer_name + '/weights')
			with tf.name_scope('biases'):
				biases = self.bias_variable([output_dim[0]])
				self.variable_summaries(biases, layer_name + '/biases')
			
			# Convolution :	
			conv = tf.nn.conv2d(input_tensor, weights, [1, stride, stride, 1], padding=padding)
			#preactivate = tf.contrib.layers.batch_norm(conv+biases, center=True, scale=True, reuse=True, is_training=phase,scope=layer_name+'/bn')
			preactivate = BNlayer(conv+biases, is_training=phase, scope=layer_name+'/bn')
			self.summary_ops.append( tf.summary.histogram(layer_name + '/pre_activations', preactivate) )
			
			# Activation :
			activations = act(preactivate, name='activation')
			self.summary_ops.append( tf.summary.histogram(layer_name + '/activations', activations) )
			
			# size handling :
			batch_size = input_dim[0]
			pad = 1 # ' SAME ' 
			if padding == 'VALID' : pad = 0 # ' VALID ' 
			
			H = 1 + (input_dim[1]+2*pad-filter_size)/stride
			W = 1 + (input_dim[2]+2*pad-filter_size)/stride
			out_dim = [ batch_size, H, W, output_dim[0] ]
			
			print("layer : "+layer_name+"/conv : input : batch x {}x{}x{} // batch x {}x{}x{}".format(input_dim[1],input_dim[2],input_dim[3],H,W,output_dim[0]))
			
			return activations, out_dim
			
	def layer_maxpoolBNAct(self,input_tensor, input_dim, phase, layer_name='maxpoolBNAct', act=tf.nn.relu, pool_size=2, poolstride=2,padding='SAME'):
		"""Reusable code for making a pool-BN-act neural net layer that divise the width and height by 2 with default parameters.
		
		It does a max_pool, batch normalize and then uses relu to nonlinearize.
		It also sets up name scoping so that the resultant graph is easy to read,
		and adds a number of summary ops.
		"""
		# Adding a name scope ensures logical grouping of the layers in the graph.
		with tf.name_scope(layer_name):
			
			# Max Pooling :
			maxpool = tf.nn.max_pool(input_tensor, [1,pool_size,pool_size,1],[1,poolstride,poolstride,1], padding=padding)
			
			with tf.name_scope('maxpool'):
				preactivate = maxpool
				#preactivate = tf.contrib.layers.batch_norm(maxpool, center=True, scale=True, reuse=True, is_training=phase,scope=layer_name+'/bn')
				self.summary_ops.append( tf.summary.histogram(layer_name + '/pre_activations', preactivate) )
			
			# Activation :
			activations = act(preactivate, name='activation')
			self.summary_ops.append( tf.summary.histogram(layer_name + '/activations', activations) )
			
			# size handling :
			batch_size = input_dim[0]
			pad = 1 # ' SAME ' 
			if padding == 'VALID' : pad = 0 # ' VALID ' 
			
			H = 1 + (input_dim[1]+2*pad-pool_size)/poolstride
			W = 1 + (input_dim[2]+2*pad-pool_size)/poolstride
			out_dim = [ batch_size, H, W, input_dim[3] ]
			
			
			print("layer : "+layer_name+"/MaxPool : input : batch x {}x{}x{} // batch x {}x{}x{}".format(input_dim[1],input_dim[2],input_dim[3],H,W,input_dim[3]))
			
			return activations, out_dim
							
	def layer_conv2dBNMaxpoolBNAct(self,input_tensor, input_dim, output_dim, phase, layer_name='conv2dBNMaxpoolBNAct', act=tf.nn.relu, filter_size=3, stride=1, pooldim=2, poolstride=2, convpadding='SAME', poolpadding='VALID'):
		"""Reusable code for making a conv-pool-BN-act neural net layer that divise the width and height by 2 with default parameters.
		
		It does a conv, a max_pool, bias add,batch normalize and then uses relu to nonlinearize.
		It also sets up name scoping so that the resultant graph is easy to read,
		and adds a number of summary ops.
		"""
		# Adding a name scope ensures logical grouping of the layers in the graph.
		with tf.name_scope(layer_name):
			
			# Convolution+BN :	
			conv, out_dim = self.layer_conv2dBNAct(input_tensor=input_tensor, input_dim=input_dim, output_dim=output_dim, phase=phase, layer_name=layer_name, act=tf.identity, filter_size=filter_size, stride=stride,padding=convpadding)
			# Max Pooling :
			actmaxpool, out_dim = self.layer_maxpoolBNAct(input_tensor=conv, input_dim=out_dim, phase=phase, layer_name=layer_name, act=tf.nn.relu, pool_size=pooldim, poolstride=poolstride,padding=poolpadding)
			
			return actmaxpool, out_dim		
			
			
				
			
			
	
	def create_network(self, scope) :
		with tf.variable_scope(scope):
			# DROPOUT + BATCH NORMALIZATION :
			keep_prob = tf.placeholder(tf.float32,name='keep_prob')
			phase = tf.placeholder(tf.bool,name='phase')
			self.summary_ops.append( tf.summary.scalar('dropout_keep_probability', keep_prob) )
			
			#Input and visual encoding layers
			#PLACEHOLDER :
			if self.useGAZEBO :
				inputs = tf.placeholder(shape=[None,self.imagesize[0]*self.imagesize[1],self.imagesize[2]],dtype=tf.float32,name='inputs')
				if self.fromState :
					inputs = tf.placeholder(shape=[None,self.imagesize[0]*self.imagesize[1], self.nbrskipframe],dtype=tf.float32,name='inputs')
					shape = inputs.get_shape().as_list()
					print('inputs : batch x {} x {}'.format(shape[1],shape[2]) )
			else :
				inputs = tf.placeholder(shape=[None,self.s_size],dtype=tf.float32,name='inputs')
			#
			#PLACEHOLDER :
			if self.useGAZEBO and self.strongCoupling :
				cmd = tf.placeholder(shape=[None,self.a_size,nbrskipframe],dtype=tf.float32,name='cmd')
			else :
				cmd = None
			#
		policy = self.build_actor(inputs, cmd, keep_prob, phase, scope+'/actor')
		Vvalue, Qvalue, actions = self.build_critic(inputs, cmd, keep_prob, phase, scope+'/critic') 
		#TODO : handled the rec placeholder and others...
		
		return inputs, actions, cmd, policy, Vvalue, Qvalue, keep_prob, phase
	
	
		
	def create_convnet(self, inputs, scope, keep_prob, phase) :
		with tf.variable_scope(scope):
			
			if self.useGAZEBO :
				if self.fromState==False :
					imageIn = tf.reshape(inputs,shape=[-1,self.imagesize[0],self.imagesize[1],self.imagesize[2]])
			
					# CONV LAYER 1 :
					shape_input = imageIn.get_shape().as_list()
					input_dim1 = [shape_input[0], shape_input[1], shape_input[2], shape_input[3]]
					nbr_filter1 = 16
					output_dim1 = [ nbr_filter1]
					#relumaxpoolconv1, input_dim2 = self.layer_conv2dBNMaxpoolBNAct(input_tensor=imageIn, input_dim=input_dim1, output_dim=output_dim1, phase=phase, layer_name='conv0MaxPool0', act=tf.nn.relu, filter_size=5, stride=3, pooldim=2, poolstride=2)
					#relumaxpoolconv1, input_dim2 = self.layer_conv2dBNMaxpoolBNAct(input_tensor=imageIn, input_dim=input_dim1, output_dim=output_dim1, phase=phase, layer_name='conv0MaxPool0', act=tf.nn.relu, filter_size=3, stride=1, pooldim=1, poolstride=1)
					relumaxpoolconv1, input_dim2 = self.layer_conv2dBNAct(input_tensor=imageIn, input_dim=input_dim1, output_dim=output_dim1, phase=phase, layer_name='conv0', act=tf.nn.relu, filter_size=10, stride=6,padding='SAME')
					rmpc1_do = tf.nn.dropout(relumaxpoolconv1,keep_prob)
		
					#LAYER STN 1 :
					#shape_inputstn = rmpc1_do.get_shape().as_list()
					#shape_inputstn = self.x_tensor.get_shape().as_list()
					#inputstn_dim = [-1, shape_inputstn[1], shape_inputstn[2], shape_inputstn[3]]
					#layerstn_name = 'stn1'
					#h_trans_def1, out_size1, self.thetas1 = self.nn_layer_stn( rmpc1_do, inputstn_dim, layerstn_name, self.keep_prob)
					#h_trans_def1, out_size1, self.thetas1 = self.nn_layer_stn( self.x_tensor, inputstn_dim, layerstn_name, self.keep_prob)
					#shape_input = h_trans_def1.get_shape().as_list()
					#input_dim2 = [shape_input[0], shape_input[1], shape_input[2], shape_input[3]]
		
					# CONV LAYER 2 :
					nbr_filter2 = 32
					output_dim2 = [ nbr_filter2]
					#relumaxpoolconv2, input_dim3 = self.layer_conv2dBNMaxpoolBNAct(input_tensor=rmpc1_do, input_dim=input_dim2, output_dim=output_dim2, phase=phase, layer_name='conv1MaxPool1', act=tf.nn.relu, filter_size=3, stride=2, pooldim=2, poolstride=2)
					#relumaxpoolconv2, input_dim3 = self.layer_conv2dBNMaxpoolBNAct(input_tensor=rmpc1_do, input_dim=input_dim2, output_dim=output_dim2, phase=phase, layer_name='conv1MaxPool1', act=tf.nn.relu, filter_size=3, stride=1, pooldim=2, poolstride=2)
					relumaxpoolconv2, input_dim3 = self.layer_conv2dBNAct(input_tensor=rmpc1_do, input_dim=input_dim2, output_dim=output_dim2, phase=phase, layer_name='conv1', act=tf.nn.relu, filter_size=4, stride=3, padding='SAME')
					rmpc2_do = tf.nn.dropout(relumaxpoolconv2,keep_prob)
		
					#LAYER STN 2 :
					#shape_inputstn = rmpc2_do.get_shape().as_list()
					#inputstn_dim = [-1, shape_inputstn[1], shape_inputstn[2], shape_inputstn[3]]
					#layerstn_name = 'stn2'
					#h_trans_def2, out_size2, self.thetas2 = self.nn_layer_stn( rmpc2_do, inputstn_dim, layerstn_name, self.keep_prob)
					#shape_input = h_trans_def2.get_shape().as_list()
					#input_dim3 = [shape_input[0], shape_input[1], shape_input[2], shape_input[3]]
		
					# CONV LAYER 3 :
					nbr_filter3 = 32
					output_dim3 = [ nbr_filter3]
					#relumaxpoolconv3, input_dim4 = self.layer_conv2dBNMaxpoolBNAct(input_tensor=rmpc2_do, input_dim=input_dim3, output_dim=output_dim3, phase=phase, layer_name='conv2MaxPool2', act=tf.nn.relu, filter_size=3, stride=1, pooldim=2, poolstride=2)
					relumaxpoolconv3, input_dim4 = self.layer_conv2dBNAct(input_tensor=rmpc2_do, input_dim=input_dim3, output_dim=output_dim3, phase=phase, layer_name='conv2', act=tf.nn.relu, filter_size=3, stride=2, padding='SAME')
					rmpc3_do = tf.nn.dropout(relumaxpoolconv3,keep_prob)
		
					#LAYER STN 3 :
					#shape_inputstn = rmpc3_do.get_shape().as_list()
					#inputstn_dim = [-1, shape_inputstn[1], shape_inputstn[2], shape_inputstn[3]]
					#layerstn_name = 'stn3'
					#h_trans_def3, out_size3, self.thetas3 = self.nn_layer_stn( rmpc3_do, inputstn_dim, layerstn_name, self.keep_prob)
					#shape_input = h_trans_def3.get_shape().as_list()
					#input_dim4 = [shape_input[0], shape_input[1], shape_input[2], shape_input[3]]
		
					# CONV LAYER 4 :
					'''
					nbr_filter4 = 128
					output_dim4 = [ nbr_filter4]
					relumaxpoolconv4, input_dim5 = self.layer_conv2dBNAct(input_tensor=rmpc3_do, input_dim=input_dim4, output_dim=output_dim4, phase=self.phase, layer_name='conv3', act=tf.nn.relu, filter_size=3, stride=1,padding='SAME')
					rmpc4_do = tf.nn.dropout(relumaxpoolconv4,self.keep_prob)		
					'''
			
					shape_conv = rmpc3_do.get_shape().as_list()
					shape_fc = [-1, shape_conv[1]*shape_conv[2]*shape_conv[3] ]
					out1 = 256
					fc_x_input = tf.reshape( rmpc3_do, shape_fc )
					convnet = fc_x_input
				else :
					convnet = tf.reshape(inputs,shape=(-1,self.s_size))
			else :
				convnet = inputs
				
			return	convnet
			
			
			
			
	
	def build_actor(self, inputs, cmd, keep_prob, phase, scope) :
		convnet = self.create_convnet( inputs, scope, keep_prob, phase)
		
		with tf.variable_scope(scope):
			shape_out = convnet.get_shape().as_list()
			# ACTOR :
			out1 = 256
			#hidden1 = self.nn_layerBN(convnet, shape_out[1], out1, phase, 'actor_layer1', act=tf.nn.relu, std=1e-2, uniform=False)
			hidden1 = self.nn_layer(convnet, shape_out[1], out1, 'actor_layer1', act=tf.nn.relu, std=1e-2)
			dropped1 = tf.nn.dropout(hidden1, keep_prob)
			
			'''
			out2 = 512
			#hidden2 = self.nn_layerBN(dropped1, out1, out2, self.phase,'layer2')
			hidden2 = self.nn_layer(dropped1, out1, out2,'actor_layer2', act=tf.nn.relu)
			dropped2 = tf.nn.dropout(hidden2, keep_prob)
			'''
			#yactor = self.nn_layerBN(dropped1, out1, self.nbrOutput, phase,'actor_layerOutput', act=tf.nn.relu, std=1e-2, uniform=False)
			yactor = self.nn_layer(dropped1, out1, self.nbrOutput, 'actor_layerOutput', act=tf.nn.relu, std=1e-2)
			#yactor = self.nn_layer(convnet, shape_out[1], self.nbrOutput, 'actor_layerOutput', act=tf.nn.relu, std=1e-2)
			#yactor = self.nn_layerBN(convnet, shape_out[1], self.nbrOutput, phase, 'actor_layerOutput', act=tf.nn.relu, std=1e-2)
			
			hidden = yactor
			
			if cmd is not None :
				shape = cmd.get_shape().as_list()
				cmd_r = tf.reshape(cmd,shape=(-1,shape[1]*shape[2]))
				hidden = tf.concat([ hidden, cmd_r], axis=1, name='concat-hidden-cmd')
				hidden = self.nn_layerBN(hidden, hidden.get_shape().as_list()[1], self.nbrOutput, phase, 'actor_hidden_concat_layer', act=tf.nn.relu, std=1e-3)
				#hidden = self.nn_layer(hidden, hidden.get_shape().as_list()[1], self.nbrOutput, 'actor_hidden_concat_layer', act=tf.nn.relu, std=1e-3)
			
			#Recurrent network for temporal dependencies
			#CAREFUL :
			#	- self.state_init
			#	- self.state_in
			# - self.state_out
			# PLACEHOLDER :
			#	- c_in
			# - h_in
			if self.rec :
				lstm_cell = tf.contrib.rnn.BasicLSTMCell(self.h_size,state_is_tuple=True)
				c_init = np.zeros((1, lstm_cell.state_size.c), np.float32)
				h_init = np.zeros((1, lstm_cell.state_size.h), np.float32)
				state_init = [c_init, h_init]
				#PLACEHOLDER :
				c_in_actor = tf.placeholder(tf.float32, [1, lstm_cell.state_size.c], name="c_in_actor")
				#
				#PLACEHOLDER :
				h_in_actor = tf.placeholder(tf.float32, [1, lstm_cell.state_size.h], name="h_in_actor")
				#
				actor_state_in = (c_in_actor, h_in_actor)
				rnn_in = tf.expand_dims(hidden, [0])
				step_size = tf.shape(imageIn)[:1]
				state_in = tf.contrib.rnn.LSTMStateTuple(c_in, h_in)
				lstm_outputs, lstm_state = tf.nn.dynamic_rnn(
					lstm_cell, rnn_in, initial_state=state_in, sequence_length=step_size,
					time_major=False)
				lstm_c, lstm_h = lstm_state
				state_out = (lstm_c[:1, :], lstm_h[:1, :])
				rnn_out = tf.reshape(lstm_outputs, [-1, self.h_size])
			else :
				rnn_out = hidden
				actor_state_init = None
				actor_state_in = None
				actor_state_out = None
				c_in_actor = None
				c_out_actor = None
				
			shape_out = rnn_out.get_shape().as_list()

			scaled_out = 	self.nn_layer(rnn_out, shape_out[1], self.a_size, 'policy', act=tf.tanh, std=1e-3, uniform=False)	
			#scaled_out = 	self.nn_layerBN(rnn_out, shape_out[1], self.a_size, phase, 'policy', act=tf.tanh, std=1e-6, uniform=False)	
			policy = tf.multiply(scaled_out, self.a_bound)	
			
			return policy
		
			
	def build_critic(self, inputs, cmd, keep_prob, phase, scope) :			
		convnet = self.create_convnet( inputs, scope, keep_prob, phase)
		
		with tf.variable_scope(scope):
			shape_out = convnet.get_shape().as_list()
			# CRITIC :
			out1 = 1024
			#hidden1 = self.nn_layerBN(convnet, self.s_size, out1, phase, 'critic_layer1', act=tf.nn.relu)
			hidden1 = self.nn_layer(convnet, shape_out[1], out1, 'critic_layer1', act=tf.nn.relu)
			dropped1 = tf.nn.dropout(hidden1, keep_prob)
			
			out2 = 512
			#hidden2 = self.nn_layerBN(convnet, shape_out[1], out2, phase, 'critic_layer2', act=tf.nn.relu)
			#hidden2 = self.nn_layerBN(dropped1, out1, out2, phase, 'critic_layer2', act=tf.nn.relu)
			hidden2 = self.nn_layer(dropped1, out1, out2,'critic_layer2', act=tf.nn.relu)
			dropped2 = tf.nn.dropout(hidden2, keep_prob)
			
			out3 = 256
			#hidden3 = self.nn_layerBN(convnet, shape_out[1], out2, phase, 'critic_layer2', act=tf.nn.relu)
			#hidden3 = self.nn_layerBN(dropped1, out1, out2, phase, 'critic_layer2', act=tf.nn.relu)
			hidden3 = self.nn_layer(dropped2, out2, out3,'critic_layer3', act=tf.nn.relu)
			dropped3 = tf.nn.dropout(hidden3, keep_prob)
			
			out4 = 256
			#hidden4 = self.nn_layerBN(convnet, shape_out[1], out2, phase, 'critic_layer2', act=tf.nn.relu)
			#hidden4 = self.nn_layerBN(dropped1, out1, out2, phase, 'critic_layer2', act=tf.nn.relu)
			hidden4 = self.nn_layer(dropped3, out3, out4,'critic_layer4', act=tf.nn.relu)
			dropped4 = tf.nn.dropout(hidden4, keep_prob)
			
			ycritic = self.nn_layer(dropped4, out4, self.nbrOutput, 'critic_layerOutput', act=tf.identity)
			#ycritic = self.nn_layer(dropped2, out2, self.nbrOutput, 'critic_layerOutput', act=tf.identity)
			#ycritic = self.nn_layer(dropped1, out1, self.nbrOutput, 'critic_layerOutput', act=tf.nn.relu)
			#ycritic = self.nn_layerBN(dropped1, out1, self.nbrOutput, phase, 'critic_layerOutput', act=tf.nn.relu)
			#ycritic = self.nn_layer(convnet, shape_out[1], self.nbrOutput, 'critic_layerOutput', act=tf.nn.relu)
			#ycritic = self.nn_layerBN(convnet, shape_out[1], self.nbrOutput, phase, 'critic_layerOutput', act=tf.nn.relu)
			
			hidden = ycritic
			
			if cmd is not None :
				shape = cmd.get_shape().as_list()
				cmd_r = tf.reshape(cmd,shape=(-1,shape[1]*shape[2]))
				hidden = tf.concat([ hidden, cmd_r], axis=1, name='concat-hidden-cmd')
				hidden = self.nn_layerBN(hidden, hidden.get_shape().as_list()[1], self.nbrOutput, phase, 'critic_hidden_concat_layer', act=tf.nn.relu, std=1e-3)
				#hidden = self.nn_layer(hidden, hidden.get_shape().as_list()[1], self.nbrOutput, 'actor_hidden_concat_layer', act=tf.nn.relu, std=1e-3)
			
			
			#Recurrent network for temporal dependencies
			#CAREFUL :
			#	- self.state_init
			#	- self.state_in
			# - self.state_out
			# PLACEHOLDER :
			#	- c_in
			# - h_in
			if self.rec :
				lstm_cell = tf.contrib.rnn.BasicLSTMCell(self.h_size,state_is_tuple=True)
				c_init = np.zeros((1, lstm_cell.state_size.c), np.float32)
				h_init = np.zeros((1, lstm_cell.state_size.h), np.float32)
				state_init = [c_init, h_init]
				#PLACEHOLDER :
				c_in = tf.placeholder(tf.float32, [1, lstm_cell.state_size.c])
				#
				#PLACEHOLDER :
				h_in = tf.placeholder(tf.float32, [1, lstm_cell.state_size.h])
				#
				state_in = (c_in, h_in)
				rnn_in = tf.expand_dims(hidden, [0])
				step_size = tf.shape(imageIn)[:1]
				state_in = tf.contrib.rnn.LSTMStateTuple(c_in, h_in)
				lstm_outputs, lstm_state = tf.nn.dynamic_rnn(
					lstm_cell, rnn_in, initial_state=state_in, sequence_length=step_size,
					time_major=False)
				lstm_c, lstm_h = lstm_state
				state_out = (lstm_c[:1, :], lstm_h[:1, :])
				rnn_out = tf.reshape(lstm_outputs, [-1, self.h_size])
			else :
				rnn_out = hidden
				
			shape_out = rnn_out.get_shape().as_list()
			#Vvalue = self.nn_layer(rnn_out, shape_out[1], 1, 'V-value', act=tf.identity)	
			
			#PLACEHOLDER :
			actions = tf.placeholder(shape=[None,self.a_size],dtype=tf.float32,name='actions')
			#
			#vvalueadvantage = self.nn_layerBN(rnn_out, shape_out[1], self.nbrOutput, self.phase, 'vvalue-advantage')
			actionadvantage = self.nn_layer( actions, self.a_size, 2*self.nbrOutput, 'action-advantage', act=tf.nn.relu)
			#actionadvantage = self.nn_layer( actions, self.a_size, self.nbrOutput, 'action-advantage', act=tf.nn.relu)
			#vvalueadvantage = self.nn_layer( Vvalue, 1, self.nbrOutput, 'vvalue-advantage')
			Vvalue = vvalueadvantage = self.nn_layer( rnn_out, shape_out[1], self.nbrOutput, 'vvalue-advantage', act=tf.nn.relu)
			
			#concat = tf.concat( [vvalueadvantage, actions], axis=1,name='concat-vvalue-actions-advantages')
			#concat = tf.nn.relu(vvalueadvantage+ actionadvantage)
			concat = tf.concat([ rnn_out, actionadvantage], axis=1, name='concat-actions-advantages')
			concat_shape = concat.get_shape().as_list()
			concat = self.nn_layer(concat, concat_shape[1], self.nbrOutput,'hidden-concat-actions-advantages', act=tf.nn.relu)
			concat_shape = concat.get_shape().as_list()
			
			#hidden = self.nn_layerBN(concat, concat_shape[1], self.nbrOutput, self.phase, 'Q-value-hidden', act=tf.nn.relu)	
			#hidden = self.nn_layer(concat, concat_shape[1], self.nbrOutput/2, 'Q-value-hidden', act=tf.nn.relu)	
			hiddenV = self.nn_layer(Vvalue, self.nbrOutput, 1, 'V-value-Advantage', act=tf.identity, std=3e-3,uniform=True)	
			hiddenA = self.nn_layer(concat, concat_shape[1], 1, 'Action-Advantage', act=tf.identity, std=3e-3,uniform=True)	
			sumhidden = hiddenV+hiddenA
			#Qvalue = self.nn_layer( Vvalue+actionadvantage, self.nbrOutput, 1, 'Q-value', act=tf.identity)	
			#Qvalue = self.nn_layer( hidden, self.nbrOutput/2, 1, 'Q-value', act=tf.identity, std=1e-3,uniform=True)	
			Qvalue = sumhidden 
			#Qvalue = self.nn_layer( sumhidden, 1, 1, 'Q-value', act=tf.identity, std=1e-3,uniform=True)	
			#Qvalue = slim.fully_connected(actionadvantage+Vvalue,1,activation_fn=None,weights_initializer=normalized_columns_initializer(0.001),biases_initializer=None)
		
		
		return Vvalue, Qvalue, actions 
		
		
			
			
			
			
	def build_loss_functions(self):
		with tf.variable_scope(self.scope) :
			#Only the worker network need ops for loss functions and gradient updating.
			#PLACEHOLDER :
			self.target_qvalue = tf.placeholder(shape=[None,1],dtype=tf.float32,name='target_qvalue')
			#
			
			#Gradients :
			qreshaped = tf.reshape(self.Qvalue,(-1,1))
			self.Qvalue_errors = tf.abs(self.target_qvalue - qreshaped)
			self.Qvalue_loss = tf.reduce_mean(self.Qvalue_errors)
			#self.Qvalue_loss = tf.reduce_mean(tf.square(self.target_qvalue - qreshaped))
			#self.Qvalue_loss = tf.losses.mean_squared_error(labels=self.target_qvalue,predictions=self.Qvalue)
			#self.Qvalue_loss = tf.squared_difference(self.target_qvalue,self.Qvalue)
			# MINIMIZATION/MAXIMIZATION OF THE REWARD(PENALTY..) :
			#MAXIMIZE :
			#self.policy_mean = tf.reduce_mean(self.policy)
			#devs_squared = tf.square(self.policy - self.policy_mean)
			#self.policy_var = tf.reduce_mean(devs_squared)
			#self.policy_loss = tf.reduce_mean(self.Qvalue-1.0/(1e-4+self.policy_var) )
			self.policy_loss = tf.reduce_mean(self.Qvalue )
			#MINIMIZE : self.policy_loss = -tf.reduce_sum(self.Qvalue_policy)
			self.loss = 0.5*self.Qvalue_loss + 0.5*self.policy_loss + self.lambda_regL2*self.l2_loss #- 0.01*self.entropy

			'''
			#Get gradients from local network using local losses
			local_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope)
			#local_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope+'/actor')
			self.var_norms = tf.global_norm(local_vars)
			
			# PLACEHOLDER :
			self.critic_gradients_action = tf.placeholder(tf.float32,[None,self.a_size],name='critic_gradients_action')#tf.gradients(tf.reduce_sum(self.Qvalue),self.actions)
			#
			
			self.critic_gradients_action_op = tf.gradients(self.Qvalue,self.actions)
			self.actor_gradients = tf.gradients(self.policy,local_vars, -self.critic_gradients_action )
			
			actor_grads,self.actor_grad_norms = tf.clip_by_global_norm(self.actor_gradients,40.0)
			critic_grads,self.critic_grad_norms = tf.clip_by_global_norm(self.critic_gradients_action_op,40.0)
			
			'''
			'''
			self.critic_gradients = tf.gradients(self.Qvalue_loss,local_vars)
			for grad in self.critic_gradients :
				if grad is not None :
					grad = tf.multiply( grad, -1.0 )
			self.apply_grads = { 'critic':self.trainer['critic'].apply_gradients(zip(self.critic_gradients,global_vars)), 'actor':self.trainer['actor'].apply_gradients(zip(self.actor_gradients,global_vars)) }
			'''
			'''
			self.apply_grads = { 'critic':self.trainer['critic'].minimize(self.Qvalue_loss), 'actor':self.trainer['actor'].apply_gradients(zip(self.actor_gradients,local_vars)) }
			'''
			local_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope)
			global_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'global')
			local_vars_actor = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope+'/actor')
			local_vars_critic = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope+'/critic')
			global_vars_actor = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'global/actor')
			global_vars_critic = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'global/critic')
			self.var_norms = tf.global_norm(local_vars)
			self.global_var_norms = tf.global_norm(global_vars)
			
			# PLACEHOLDER :
			self.critic_gradients_action = tf.placeholder(tf.float32,[None,self.a_size],name='critic_gradients_action')#tf.gradients(tf.reduce_sum(self.Qvalue),self.actions)
			#
			
			self.critic_gradients_action_op = tf.gradients(self.Qvalue,self.actions)
			#self.critic_gradients_action_op = tf.gradients(self.policy_loss,self.actions)
			self.actor_gradients = tf.gradients(self.policy,local_vars_actor, -self.critic_gradients_action )
			#self.actor_gradients = tf.gradients(self.policy,local_vars, -self.critic_gradients_action )
			
			self.critic_gradients = tf.gradients(self.Qvalue_loss,local_vars_critic)
			#self.critic_gradients = tf.gradients(self.Qvalue_loss,local_vars)
			#self.critic_gradients = tf.gradients(self.loss,local_vars)
			
			'''
			for grad in self.critic_gradients :
				if grad is not None :
					grad = tf.multiply( grad, -1.0 )
			'''
			
			actor_grads,self.actor_grad_norms = tf.clip_by_global_norm(self.actor_gradients,40.0)
			critic_grads,self.critic_grad_norms = tf.clip_by_global_norm(self.critic_gradients,40.0)
			
			
			#self.apply_grads = { 'critic':self.trainer['critic'].minimize(self.Qvalue_loss), 'actor':self.trainer['actor'].apply_gradients(zip(self.actor_gradients,global_vars)) }
			#self.apply_grads = { 'critic':self.trainer['critic'].apply_gradients( zip(self.critic_gradients,global_vars) ), 'actor':self.trainer['actor'].apply_gradients(zip(self.actor_gradients,global_vars)) }
			self.apply_grads = { 'critic':self.trainer['critic'].apply_gradients( zip(self.critic_gradients,global_vars_critic) ), 'actor':self.trainer['actor'].apply_gradients(zip(self.actor_gradients,global_vars_actor)) }
			
			
			
	def predict_actor(self, sess, inputs, cmd=None, phase=False) :
		if cmd is None :
			feed_dict = {self.inputs:inputs,
			self.keep_prob:1.0,
			self.phase:phase
			}
		else :
			feed_dict = {self.inputs:inputs,
			self.cmd:cmd,
			self.keep_prob:1.0,
			self.phase:phase
			}
		return sess.run( [self.policy], feed_dict=feed_dict)[0]
		
	def predict_critic(self, sess, inputs, actions, cmd=None, phase=False) :
		if cmd is None :
			feed_dict = {self.inputs:inputs,
			self.actions:actions,
			self.keep_prob:1.0,
			self.phase:phase
			}
		else :
			feed_dict = {self.inputs:inputs,
			self.actions:actions,
			self.cmd:cmd,
			self.keep_prob:1.0,
			self.phase:phase
			}
		return sess.run( [self.Qvalue], feed_dict=feed_dict)[0]
		
	def predict_actor_target(self, sess, inputs, cmd=None, phase=False) :
		if cmd is None :
			feed_dict = {self.t_inputs:inputs,
			self.t_keep_prob:1.0,
			self.t_phase:phase
			}
		else :
			feed_dict = {self.t_inputs:inputs,
			self.t_cmd:cmd,
			self.t_keep_prob:1.0,
			self.t_phase:phase
			}
		return sess.run( [self.t_policy], feed_dict=feed_dict)[0]
		
	def predict_critic_target(self, sess, inputs, actions, cmd=None, phase=False) :
		if cmd is None :
			feed_dict = {self.t_inputs:inputs,
			self.t_actions:actions,
			self.t_keep_prob:1.0,
			self.t_phase:phase
			}
		else :
			feed_dict = {self.t_inputs:inputs,
			self.t_actions:actions,
			self.t_cmd:cmd,
			self.t_keep_prob:1.0,
			self.t_phase:phase
			}
		return sess.run( [self.t_Qvalue], feed_dict=feed_dict)[0]
		
			
























class Worker():
	def __init__(self,master_network,game,replayBuffer,name, model_path, global_episodes, rec=False, updateT=1e-2, nbrStepPerReplay=15, useGAZEBO=True, fromState=True, coupledSystem=True, strongCoupling=True):
		self.useGAZEBO = useGAZEBO
		self.fromState = fromState
		self.coupledSystem = coupledSystem
		self.strongCoupling = strongCoupling
		
		self.master_network = master_network
		self.name = "worker_" + str(name)
		self.trainer = { 'actor':tf.train.AdamOptimizer(learning_rate=lr), 'critic':tf.train.AdamOptimizer(learning_rate=lr*1e0)}
		self.local_network = AC_Network(self.master_network.imagesize,self.master_network.s_size,self.master_network.h_size,self.master_network.a_size,self.master_network.a_bound,self.name,self.trainer,tau=self.master_network.tau,rec=rec,useGAZEBO=self.useGAZEBO, fromState=self.fromState, strongCoupling=self.strongCoupling)
		self.number = name        
		self.model_path = model_path
		self.global_episodes = global_episodes
		self.increment = self.global_episodes.assign_add(1)
		
		self.episode_rewards = []
		self.episode_lengths = []
		self.episode_mean_values = []
		self.episode_max_values = []
		self.episode_min_values = []
		
		self.summary_writer = tf.summary.FileWriter(self.model_path+"/training_logs/train_"+str(self.number))
		self.test_summary_writer = tf.summary.FileWriter(self.model_path+"/training_logs/train_test"+str(self.number))

		self.rec = rec
		self.updateT = updateT
		
		# let us update the local network towards the base global master network :
		#self.update_ops_thread = update_thread_graph('global',self.name,1.0)
		#self.update_ops_thread_target = update_thread_graph('global_target',self.name+'_target',1.0)
		self.update_ops_thread_init = update_thread_graph('global',self.name,1.0)
		self.update_ops_thread_target_init = update_thread_graph('global_target',self.name+'_target',1.0)
		self.update_ops_thread = update_thread_graph('global',self.name,self.updateT)
		self.update_ops_thread_target = update_thread_graph('global_target',self.name+'_target',self.updateT)
		self.update_ops_target_init = update_target_graph('global','global_target',1.0)
		self.update_ops_target = update_target_graph('global','global_target',self.master_network.tau)
		
		#self.actions = self.actions = np.identity(a_size,dtype=bool).tolist()
		self.actions = np.identity(a_size,dtype=np.float32).tolist()
		self.env = game
		self.rBuffer = replayBuffer
		self.nbrStepPerReplay = nbrStepPerReplay
		if self.number != 0 :
			self.nbrStepPerReplay = 2*self.nbrStepPerReplay
        
	def train(self,rollout,sess,gamma,bootstrap_value):
		rollout = np.array(rollout)
		observations = np.vstack(rollout[:,0]) #np.reshape( rollout[:,0], newshape=(-1,s_size) )
		actions = np.vstack(rollout[:,1]) #np.reshape( rollout[:,1], newshape=(-1,a_size) )
		rewards = np.vstack(rollout[:,2]) #np.reshape( rollout[:,2], newshape=(-1,1) )
		next_observations = np.vstack(rollout[:,3]) #np.reshape( rollout[:,3], newshape=(-1,s_size) )
		terminate = np.vstack(rollout[:,4]) #np.reshape(rollout[:,4],newshape=(-1,1) )
		indexes = np.vstack(rollout[:,5])
		batch_size = rollout.shape[0]
		
		if self.coupledSystem :
			cmd = np.vstack( rollout[:,6] )
			next_cmd = np.vstack( rollout[:,7] )
			
		
		self.target_qvalue_num = []
		for k in range(batch_size):
			#self.target_qvalue_num.append(rewards[k,0] + gamma * bootstrap_value[k,0])
			if terminate[k,0]:
				self.target_qvalue_num.append(rewards[k,0])
			else:
				self.target_qvalue_num.append(rewards[k,0] + gamma * bootstrap_value[k,0])
		self.target_qvalue_num = np.reshape(self.target_qvalue_num, (batch_size, 1))

		vobs = observations
		
		if self.rec :
			rnn_state = self.local_AC.state_init
			feed_dict = {self.local_AC.target_qvalue:self.target_qvalue_num,
				self.local_AC.inputs:vobs,
				self.local_AC.actions:actions,
				self.local_AC.state_in[0]:rnn_state[0],
				self.local_AC.state_in[1]:rnn_state[1],
				self.local_AC.keep_prob:self.local_AC.dropoutK,
				self.local_AC.phase:True}
		else :
			# TRAIN CRITIC :
			if self.strongCoupling == False :
				feed_dict = {self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.inputs:vobs,
				self.local_network.actions:actions,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:True}
			else :
				feed_dict = {self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.inputs:vobs,
				self.local_network.actions:actions,
				self.local_network.cmd:cmd,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:True}
		
			errors, v_l, v_n,_ = sess.run([self.local_network.Qvalue_errors,
				self.local_network.Qvalue_loss,
				self.local_network.var_norms,
				self.local_network.apply_grads['critic']],
				feed_dict=feed_dict)
			
			#CREATE VALUES :
			if self.strongCoupling == False :
				a_out = self.local_network.predict_actor(sess, vobs,phase=True)
			else :
				a_out = self.local_network.predict_actor(sess, vobs, cmd, phase=True)
			
			if self.strongCoupling == False :
				feed_dict = {self.local_network.inputs:vobs,
				self.local_network.actions:a_out,
				self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:False}
			else :
				feed_dict = {self.local_network.inputs:vobs,
				self.local_network.actions:a_out,
				self.local_network.cmd:cmd,
				self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:False}
			
			critic_gradients_action, c_g_n = sess.run([self.local_network.critic_gradients_action_op, self.local_network.critic_grad_norms],
				feed_dict = feed_dict)
				#/batch_size
				#TODO : decide about the importance of the division by batch_size....
			
			#TRAIN ACTOR :
			'''
			feed_dict = {self.local_network.inputs:vobs,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:True,
				self.local_network.critic_gradients_action:critic_gradients_action[0]}
		
			p_l, a_g_n,_ = sess.run([self.local_network.policy_loss,
				self.local_network.actor_grad_norms,
				self.local_network.apply_grads['actor']],
				feed_dict=feed_dict)	
			'''
			if self.strongCoupling == False :
				feed_dict = {self.local_network.actions:actions,
				self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.inputs:vobs,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:True,
				self.local_network.critic_gradients_action:critic_gradients_action[0]}
			else :
				feed_dict = {self.local_network.actions:actions,
				self.local_network.target_qvalue:self.target_qvalue_num,
				self.local_network.inputs:vobs,
				self.local_network.cmd:cmd,
				self.local_network.keep_prob:self.master_network.dropoutK,
				self.local_network.phase:True,
				self.local_network.critic_gradients_action:critic_gradients_action[0]}
		
			p_l, a_g_n,_ = sess.run([self.local_network.policy_loss,
				self.local_network.actor_grad_norms,
				self.local_network.apply_grads['actor']],
				feed_dict=feed_dict)
		
		#UPDATE THE PER :
		for (idx, new_error) in zip(indexes,errors) :
			new_priority = self.rBuffer.priority(new_error)
			#print( 'prior = {} / {}'.format(new_priority,self.rBuffer.total()) )
			self.rBuffer.update(idx,new_priority)
			
		# UPDATE OF THE TARGET NETWORK:
		#if self.number == 0 :
		sess.run(self.update_ops_target)
		
		# UPDATE OF THE THREAD NETWORK TO BASE NETWORK :
		sess.run(self.update_ops_thread)
		sess.run(self.update_ops_thread_target)					
				
		return v_l/batch_size, p_l/batch_size, a_g_n, c_g_n, v_n
		
		
		    
	def work(self,max_episode_length,gamma,sess,coord,saver):
		if self.useGAZEBO :
			LoopRate = rospy.Rate(100)
		episode_count = sess.run(self.global_episodes)
		summary_count = 0
		total_steps = 0
		logit = 0
		reward_scaler = 1.0
		dummy_action = np.zeros(a_size)
		a_noise = dummy_action
		a_backup =dummy_action
		
		print ("Starting worker " + str(self.number))
		make_gif_log = False
		with sess.as_default(), sess.graph.as_default():                 
			if self.number == 0:
				sess.run(self.update_ops_target_init)
				print('Target synchronized...')
			
			sess.run(self.update_ops_thread_init)
			sess.run(self.update_ops_thread_target_init)
			print('Thread {} synchronized...'.format(self.number))
			
			
			
			while not coord.should_stop():
				try :
					episode_buffer = []
					episode_values = []
					episode_frames = []
					episode_reward = 0
					episode_step_count = 0
					q_loss = 0
					d = False

					#Let us start a new episode :
					if threadExploration or self.number == 0 :
						if not useGAZEBO :
							if self.number == 0 :
								print('ENVIRONMENT RESETTED !')
							s = self.env.reset()
							if self.number == 0 :
								self.env.render()
							s = np.reshape(s,(-1,self.local_network.s_size))
							#s = process_frame(s)
						else :
							s = self.env.reset()
							if self.number == 0 :
								print('ENVIRONMENT RESETTED !')
							obs,dr,ddone,_ = envstep(self.env,dummy_action, self.fromState)
							s = obs[0]
							cmd = obs[1]
							if self.fromState==False :
								s = preprocess(s, img_size[0], img_size[1] )
						
						#episode_frames.append(s)
					
						if self.rec :
							#TODO :
							rnn_state = self.master_network.state_init
				
						remainingSteps = max_episode_length   
						actions = []   
						a_noise = np.zeros(a_size)
						time_log = 0
						time_log_print = 50
						time_mean = 0.0
						
						# START EPISODE :
						#
						#
						while d == False :
							start = time()
							remainingSteps -= 1
							
							#Take an action using probabilities from policy network output.
							if self.rec :
								rnn_state_q = rnn_state
								a,v,rnn_state = sess.run([self.local_AC.policy,self.local_AC.Vvalue,self.local_AC.Qvalue,self.local_AC.state_out], 
									feed_dict={self.local_AC.inputs:s,
									self.local_AC.state_in[0]:rnn_state[0],
									self.local_AC.state_in[1]:rnn_state[1],
									self.local_AC.keep_prob:1.0,
									self.local_AC.phase:False})
								#summary, q = sess.run([self.local_AC.merged_summary, self.local_AC.Qvalue], 
								q = sess.run([ self.local_AC.Qvalue], 
										feed_dict={self.local_AC.inputs:s,
									self.local_AC.state_in[0]:rnn_state_q[0],
									self.local_AC.state_in[1]:rnn_state_q[1],
									self.local_AC.actions:a,
									self.local_AC.keep_prob:1.0,
									self.local_AC.phase:False})
							else :
								if self.number == 0 :
									if self.strongCoupling == False :
										a = self.master_network.predict_actor(sess, s)
									else :
										a = self.master_network.predict_actor(sess, s, cmd)
								else :
									if self.strongCoupling == False :
										a = self.local_network.predict_actor(sess, s)
									else :
										a = self.local_network.predict_actor(sess, s, cmd)
								
							
							#EXPLORATION NOISE :
							'''
							eps_greedy_prob = 0.4/(1+episode_count/10)
							if np.random.rand() < eps_greedy_prob :
								scale = self.master_network.a_bound/1.0
								#a_noise = np.random.normal(loc=0.0,scale=scale,size=a[0].shape)
								a_noise = np.random.uniform(low=-scale,high=scale,size=a[0].shape)
								#a[0] = a_noise
								a[0] += a_noise
							'''
							
							# ORNSTEIN-UHLENBECK EXPLORATION NOISE : variable scale...
							if True : #episode_count%2 and (self.coupledSystem==False):
								scale = self.local_network.a_bound/dividerNoise#2.0
								theta = 0.15
								sigma = 0.3*scale
								a_backup = a[0]
								dt = 1e-0
								for i in range(a_size) :
									a_noise[i] += theta*(0.0-a_noise[i])*dt+sigma*np.sqrt(dt)*np.random.normal(loc=0.0,scale=1.0)
									a[0,i] += a_noise[i]
							
							'''
							a_noise =  (1. / (1. + episode_count))
							a[0] += a_noise
							'''
							
							# SAVE FOR THE RL FRAMEWORK UPDATES :
							a_out = a
							
							# THIS IS NOT PART OF THE RL SYSTEM ...
							#
							if self.coupledSystem :
								if cmd is None:
									cmd = np.zeros((1,a_size))
								
									
								for i in range(a_size) :
									if NLonly :
										a[0,i] = cmd[0,i,nbrskipframe-1]
									else :
										a[0,i] += cmd[0,i,nbrskipframe-1]
							#
							#
							
							
							if self.useGAZEBO :
								obs1, r, d, _ = envstep(self.env, a[0], self.fromState)
								s1 = obs1[0]
								cmd1 = obs1[1]
							else :
								s1, r, d, _ = self.env.step(a)
								if self.number == 0:
									self.env.render()
									
							#RESTORE FOR THE RL FRAMEWORK :
							#
							a = a_out
							#
							#	
							
							
							if self.useGAZEBO :
								if self.fromState==False:
									s1 = preprocess(s1, img_size[0], img_size[1] )
							else :
								s1 = np.reshape(s1,(-1,self.master_network.s_size))
							
							
							#bounding the rewards :
							if np.abs(r) > reward_bound :
								r = reward_bound*np.sign(r)
								
							r /= reward_scaler
							
									
							#if self.number == 0 :
							#	rospy.loginfo('state : {} ; policy : {} ; reward : {} ; noise : {}'.format(s, a_backup, r, a_noise) )
								
							
							q = None
							if self.number == 0 :
								if self.strongCoupling == False :
									q = self.master_network.predict_critic(sess,s,a)
								else :
									q = self.master_network.predict_critic(sess,s,a,cmd)
							else :
								if self.strongCoupling == False :
									q = self.local_network.predict_critic(sess,s,a)
								else :
									q = self.local_network.predict_critic(sess,s,a,cmd)
							
							
							if self.coupledSystem == False :
								#step = [s,a,r,s1,d,q[0]]
								step = EXP(s,a,s1,r,d)
							else :
								step = [s,a,r,s1,d,q[0],cmd,cmd1]
							episode_buffer.append(step)
							
							episode_values.append(q[0])
							actions.append(a[0])
							

							episode_reward += r
							s = s1            
							if self.useGAZEBO :
								cmd = cmd1        
							total_steps += 1
							episode_step_count += 1
							
							if remainingSteps < 0 :
								d = True
							
							
							if logit > 100 :
								#NETWORK-RELATED SUMMARIES :
								if self.number == 0:
									if self.strongCoupling == False :
										feed_dict = {self.master_network.inputs:s,
										self.master_network.actions:a,
										self.master_network.keep_prob:1.0,
										self.master_network.phase:False,
										self.master_network.t_inputs:s,
										self.master_network.t_actions:a,
										self.master_network.t_keep_prob:1.0,
										self.master_network.t_phase:False}
									else :
										feed_dict = {self.master_network.inputs:s,
										self.master_network.actions:a,
										self.master_network.cmd:cmd,
										self.master_network.keep_prob:1.0,
										self.master_network.phase:False,
										self.master_network.t_inputs:s,
										self.master_network.t_actions:a,
										self.master_network.t_cmd:cmd,
										self.master_network.t_keep_prob:1.0,
										self.master_network.t_phase:False}
									
									summary = sess.run(self.master_network.summary_ops, 
										feed_dict=feed_dict)
									self.test_summary_writer.add_summary(summary,summary_count)
									self.test_summary_writer.flush()
									summary_count += 1
								else :
									if self.strongCoupling == False :
										feed_dict = {self.local_network.inputs:s,
										self.local_network.actions:a,
										self.local_network.keep_prob:1.0,
										self.local_network.phase:False,
										self.local_network.t_inputs:s,
										self.local_network.t_actions:a,
										self.local_network.t_keep_prob:1.0,
										self.local_network.t_phase:False}
									else :
										feed_dict = {self.local_network.inputs:s,
										self.local_network.actions:a,
										self.local_network.cmd:cmd,
										self.local_network.keep_prob:1.0,
										self.local_network.phase:False,
										self.local_network.t_inputs:s,
										self.local_network.t_actions:a,
										self.local_network.t_cmd:cmd,
										self.local_network.t_keep_prob:1.0,
										self.local_network.t_phase:False}
									
									summary = sess.run(self.local_network.summary_ops, 
										feed_dict=feed_dict)
									self.test_summary_writer.add_summary(summary,summary_count)
									self.test_summary_writer.flush()
									summary_count += 1
								
								logit = 0
							else :
								logit += 1
							
							# TRAINING :
							#
							#if self.rBuffer.counter > self.nbrStepPerReplay:
							#	v_l,p_l,a_g_n,c_g_n,v_n = self.train_on_rBuffer(sess)
							#	q_loss += np.mean(v_l)
							#
							#
							
							if self.useGAZEBO :
								LoopRate.sleep()
								
							end = time()
							
							if self.number == 0 :
								if time_log == time_log_print :
									time_log = 0
									time_mean += end-start
									time_mean /= time_log_print
									print('EXECUTION TIME : %.4f' % time_mean )
									time_mean = 0.0
								else :
									time_mean += end - start
									time_log += 1

						#END OF EPISODE WHILE LOOP...
						
						# DATA HANDLING :
						#
						#	
						if self.useGAZEBO :
							self.env.setPause(True)
						
						actions = np.vstack(actions)
						if self.number == 0 :
							sentence = 'episode:{} / step:{} / mean action: {} / dev action : {} / cumulative reward: {}'.format(episode_count,episode_step_count,np.mean( actions), np.std(actions),episode_reward)
							if self.useGAZEBO :
								rospy.loginfo(sentence)
							else :
								print(sentence)
	
						self.episode_rewards.append(episode_reward)
						self.episode_lengths.append(episode_step_count)
						self.episode_mean_values.append(np.mean(episode_values))
						self.episode_max_values.append(np.max(episode_values))
						self.episode_min_values.append(np.min(episode_values))


						#Let us add this episode_buffer to the replayBuffer :
						for el in episode_buffer :
							init_priority = self.rBuffer.priority( np.abs(el.r) )
							self.rBuffer.add(el,init_priority)
						
						
						# Periodically save gifs of episodes, model parameters, and summary statistics.
						if self.number == 0 :
							if episode_count % 5 == 0 and episode_count != 0:
								if self.name == 'worker_0' and episode_count % 25 == 0:
									time_per_step = 0.05
									#images = np.array(episode_frames)
									#if make_gif_log :
									#	make_gif(images,'./frames/image'+str(episode_count)+'.gif',
									#		duration=len(images)*time_per_step,true_image=True,salience=False)
							if episode_count % 5 == 0 and self.name == 'worker_0':
								saver.save(sess,self.model_path+'/model-'+str(episode_count)+'.cptk')
								print ("Saved Model")
							
							sess.run(self.increment)
						#
						#-----------------------------------------------------
						
						# TRAINING :
						#
						#
						if self.rBuffer.counter > self.nbrStepPerReplay:
							for i in range(self.nbrStepPerReplay) :
								v_l,p_l,a_g_n,c_g_n,v_n = self.train_on_rBuffer(sess)
								q_loss += np.mean(v_l)
						
						#
						#---------------------------------------------------
					#END OF IF SELF.NUMBER == 0
					
					# Update the network using the experience replay buffer:
					if self.rBuffer.counter > self.nbrStepPerReplay:
						v_l,p_l,a_g_n,c_g_n,v_n = self.train_on_rBuffer(sess)	
								
						if self.number == 0 :
							mean_reward = np.mean(self.episode_rewards[-5:])
							mean_length = np.mean(self.episode_lengths[-5:])
							mean_value = np.mean(self.episode_mean_values[-5:])
							max_value = np.mean(self.episode_max_values[-5:])
							min_value = np.mean(self.episode_min_values[-5:])
							summary = tf.Summary()
							summary.value.add(tag='Perf/Reward', simple_value=float(mean_reward))
							summary.value.add(tag='Perf/Length', simple_value=float(mean_length))
							summary.value.add(tag='Perf/Value', simple_value=float(mean_value))
							summary.value.add(tag='Perf/MaxValue', simple_value=float(max_value))
							summary.value.add(tag='Perf/MinValue', simple_value=float(min_value))
							summary.value.add(tag='Losses/Value Loss', simple_value=float(v_l))
							summary.value.add(tag='Losses/Policy Loss', simple_value=float(p_l))
							#summary.value.add(tag='Losses/Entropy', simple_value=float(e_l))
							summary.value.add(tag='Losses/Actor_Grad Norm', simple_value=float(a_g_n))
							summary.value.add(tag='Losses/Critic_Grad Norm', simple_value=float(c_g_n))
							summary.value.add(tag='Losses/Var Norm', simple_value=float(v_n))
							summary.value.add(tag='Losses/Q Loss', simple_value=float(q_loss)/(episode_step_count+1))
							self.summary_writer.add_summary(summary, episode_count)
							self.summary_writer.flush()
							episode_count += 1
						
					else :
						sleep(5)

				except Exception as e :
					print('EXCEPTION HANDLED : '+str(e)+' :: '+str(sys.exc_info()[0]) )


	def train_on_rBuffer(self,sess) :
		a1 = None
		prioritysum = self.rBuffer.total()
		#idxSteps = np.random.randint(low=0, high=len(self.rBuffer), size=self.nbrStepPerReplay)
		randexp = np.random.random(size=self.nbrStepPerReplay)*prioritysum
		minibatch = list()
		for i in range(self.nbrStepPerReplay):
			try :
				el = self.rBuffer.get(randexp[i])
				minibatch.append(el)
			except TypeError as e :
				continue
				#print('REPLAY BUFFER EXCEPTION...')
		
		rollout = np.vstack( [ [el[2].s, el[2].a, el[2].r, el[2].s1, el[2].done, el[0]] for el in minibatch ] )
		
		s1 = np.vstack(rollout[:,3])
		if self.strongCoupling :
			cmd1 = np.vstack(rollout[:,7])
		
		# Since we don't know what the true final return is, we "bootstrap" from our current
		# q value estimation that is done by the target network of the master network on which we apply the gradients...
		if self.rec :
			a1 = sess.run(self.local_AC.policy,
			feed_dict={self.local_AC.inputs:s1,
			self.local_AC.state_in[0]:rnn_state[0],
			self.local_AC.state_in[1]:rnn_state[1],
			self.local_AC.keep_prob:1.0,
			self.local_AC.phase:False})
			q1 = sess.run(self.local_AC.Qvalue, 
			feed_dict={self.local_AC.inputs:s1,
			self.local_AC.state_in[0]:rnn_state[0],
			self.local_AC.state_in[1]:rnn_state[1],
			self.local_AC.actions:a,
			self.local_AC.keep_prob:1.0,
			self.local_AC.phase:False})[0,0]
		else :
			if self.strongCoupling == False :
				#if self.number != 0 :
				a1 = self.local_network.predict_actor_target( sess, s1, phase=True)
				q1 = self.local_network.predict_critic_target( sess, s1, a1, phase=True)
				#else :
				#	a1 = self.master_network.predict_actor_target( sess, s1, phase=True)
				#	q1 = self.master_network.predict_critic_target( sess, s1, a1, phase=True)
			else :
				a1 = self.local_network.predict_actor_target( sess, s1, cmd1, phase=True)
				q1 = self.local_network.predict_critic_target( sess, s1, a1, cmd1, phase=True)
				
		return self.train( rollout,sess,gamma,q1)
	
	
		
	def plot_qvalues(self, sess) :
		h = 100
		step = 2.0/h
		'''
		 -1.0:step:1.0
		state2 = -1.0:step:1.0
		'''
		
		
tf.reset_default_graph()


with tf.device("/cpu:0"): 
	global_episodes = tf.Variable(0,dtype=tf.int32,name='global_episodes',trainable=False)
	trainer = { 'actor':tf.train.AdamOptimizer(learning_rate=lr), 'critic':tf.train.AdamOptimizer(learning_rate=lr*10.0)}
	master_network = AC_Network(imagesize,s_size,h_size,a_size,a_bound,'global',trainer,tau=updateTauTarget,rec=rec,useGAZEBO=useGAZEBO, fromState=fromState, strongCoupling=strongCoupling) # Generate global network 
	workers = []
	replayBuffer = PER(capacity=maxReplayBufferSize,alpha=alphaPER)
	
	# Create worker classes
	for i in range(num_workers):
		game = None
		if useGAZEBO :
			if threadExploration == False :
				game = env[0]
			else :	
				game = Swarm1GazeboRL(base_port,energy_based, coupledSystem=coupledSystem, fromState=fromState, equilibriumBased=equilibriumBased)
				base_port += 1
				game.make()
				print('\n\nCreation of the environment :: wait for 2 sec...\n\n')
				time.sleep(2)
				game.reset()
				game.setPause(False)
				env.append( game )
		else :
			game = gym.make('Pendulum-v0')
			#game = gym.make('MountainCarContinuous-v0')
		workers.append(Worker(master_network,game,replayBuffer,i,model_path,global_episodes,rec,updateT,nbrStepsPerReplay,useGAZEBO=useGAZEBO, fromState=fromState, coupledSystem=coupledSystem, strongCoupling=strongCoupling))
	saver = tf.train.Saver(max_to_keep=5)

with tf.Session() as sess:
	coord = tf.train.Coordinator()
	if load_model == True:
		print ('Loading Model...')
		ckpt = tf.train.get_checkpoint_state(model_path)
		saver.restore(sess,ckpt.model_checkpoint_path)
	else:
		sess.run(tf.global_variables_initializer())
	
	print('MODEL INITIALIZED....')
	
	# This is where the asynchronous magic happens.
	# Start the "work" process for each worker in a separate threat.
	worker_threads = []
	for worker in workers:
		worker_work = lambda: worker.work(max_episode_length,gamma,sess,coord,saver)
		t = threading.Thread(target=(worker_work))
		t.start()
		sleep(0.5)
		worker_threads.append(t)
	coord.join(worker_threads)

  
for envi in env :
	envi.close()


