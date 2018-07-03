##### 패키지 불러오기
import pandas as pd
import os
import tensorflow as tf
import sklearn.metrics as skm
import time
from collections import Counter

##### 이미지 전처리, 네트워크 함수
NUM_CLASSES = 2

def set_input(img, label):
    np.random.seed(1234)
    idx = np.random.permutation(len(img))
    tr_idx = idx[:round(0.8 * len(idx))]
    ts_idx = idx[round(0.8 * len(idx)):]

    train_img = img[tr_idx]
    train_label = label[tr_idx]
    test_img = img[ts_idx]
    test_label = label[ts_idx]

    train_img_tensor = tf.constant(train_img)
    train_label_tensor = tf.constant(train_label)
    test_img_tensor = tf.constant(test_img)
    test_label_tensor = tf.constant(test_label)

    return train_img_tensor, train_label_tensor, test_img_tensor, test_label_tensor, tr_idx, ts_idx
	
# string 텐서를 img 텐서로 변환 후 crop
def input_tensor(img_path, label):
    label_crop = tf.one_hot(label, NUM_CLASSES)
    
    img_file = tf.read_file(img_path)
    img_decoded = tf.image.decode_png(img_file)
    img_crop = tf.image.crop_to_bounding_box(img_decoded, 135, 0, 135, 480)
    img_float = tf.to_float(img_crop)
    img_crop = tf.random_crop(img_float, size=[135, 480, 3])
    label = tf.one_hot(label, NUM_CLASSES)
    

    return tf.reshape(img_crop, [-1,135,480,3]), tf.reshape(label, [-1,3])	
	
def make_batch(dataset):
    dataset_0 = dataset.filter(lambda x,y: tf.reshape(tf.equal(tf.argmax(y), tf.argmax(tf.constant([1,0], tf.float32))), []))
    dataset_1 = dataset.filter(lambda x,y: tf.reshape(tf.equal(tf.argmax(y), tf.argmax(tf.constant([0,1], tf.float32))), [])).repeat()
    
    datasets = tf.data.Dataset.zip((dataset_0, dataset_1))
    datasets = datasets.flat_map(lambda ex_0, ex_1: tf.data.Dataset.from_tensors(ex_0).concatenate(tf.data.Dataset.from_tensors(ex_1)))
    
    return datasets

	
def conv2d(x, num_outputs, batch_norm=True):
    if batch_norm is True:
        conv_bn = tf.contrib.layers.batch_norm
    else:
        conv_bn = None

    conv = tf.contrib.layers.conv2d(inputs=x,
                                    num_outputs=num_outputs,
                                    kernel_size=(3, 3),
                                    normalizer_fn=conv_bn,
                                    activation_fn=tf.nn.relu)
    return conv
	
def pooling(x):
    pool = tf.contrib.layers.max_pool2d(inputs=x, kernel_size=(2, 2))
    return pool
	
def dense(x, output, fn=tf.nn.relu, batch_norm=True):
    if batch_norm is True:
        fc_bn = tf.contrib.layers.batch_norm
    else:
        fc_bn = None
    fc = tf.contrib.layers.fully_connected(inputs=x,
                                           num_outputs=output,
                                           normalizer_fn=fc_bn,
                                           activation_fn=fn)
    return fc
	
class VGG16():
    def __init__(self, x, y, bn, classification):
        
        with tf.name_scope("input"):
            self.x = x
            self.y = y

        with tf.name_scope("layer_1"):
            conv1 = conv2d(x, 64, batch_norm=bn)
            conv2 = conv2d(conv1, 64, batch_norm=bn)
            pool1 = pooling(conv2)

        with tf.name_scope("layer_2"):
            conv3 = conv2d(pool1, 128, batch_norm=bn)
            conv4 = conv2d(conv3, 128, batch_norm=bn)
            pool2 = pooling(conv4)

        with tf.name_scope("layer_3"):
            conv5 = conv2d(pool2, 256, batch_norm=bn)
            conv6 = conv2d(conv5, 256, batch_norm=bn)
            conv7 = conv2d(conv6, 256, batch_norm=bn)
            pool3 = pooling(conv7)

        with tf.name_scope("layer_4"):
            conv8 = conv2d(pool3, 512, batch_norm=bn)
            conv9 = conv2d(conv8, 512, batch_norm=bn)
            conv10 = conv2d(conv9, 512, batch_norm=bn)
            pool4 = pooling(conv10)

        with tf.name_scope("layer_5"):
            conv11 = conv2d(pool4, 512, batch_norm=bn)
            conv12 = conv2d(conv11, 512, batch_norm=bn)
            conv13 = conv2d(conv12, 512, batch_norm=bn)
            pool5 = pooling(conv13)

        with tf.name_scope("FC_layer"):
            fc1 = tf.layers.flatten(pool5)
            fc2 = dense(fc1, 4096, batch_norm=bn)
            fc3 = dense(fc2, 4096, batch_norm=bn)

        self.learning_rate = tf.placeholder(tf.float32)
        self.global_step = tf.Variable(0, trainable=False, name='global_step')

        if classification is True:
            self.logits = dense(fc3, NUM_CLASSES, fn=None, batch_norm=True)
            self.loss = tf.losses.softmax_cross_entropy(onehot_labels=self.y, logits=self.logits)
            self.lr_decay = tf.train.exponential_decay(self.learning_rate, self.global_step, 1000, 0.9, staircase=True)
            self.extra_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            
            with tf.control_dependencies(self.extra_update_ops):
                self.adam = tf.train.AdamOptimizer(self.lr_decay).minimize(self.loss,
                                                                           global_step=self.global_step)
                self.sgd = tf.train.GradientDescentOptimizer(self.lr_decay).minimize(self.loss,
                                                                                     global_step=self.global_step)
                self.rms = tf.train.RMSPropOptimizer(self.lr_decay).minimize(self.loss,
                                                                             global_step=self.global_step)
                self.momentum = tf.train.MomentumOptimizer(self.lr_decay, momentum=0.9).minimize(self.loss,
                                                                                                 global_step=self.global_step)

            self.y_prob = tf.nn.softmax(self.logits)
            self.y_pred = tf.argmax(self.y_prob, 1)

            self.correct_prediction = tf.equal(self.y_pred, tf.arg_max(y, 1))
            self.accuracy = tf.reduce_mean(tf.cast(self.correct_prediction, tf.float32))

            tf.summary.scalar("accuray", self.accuracy)
            tf.summary.scalar("loss", self.loss)

        else:
            self.logits = tf.layers.dense(fc3, 1, activation=tf.nn.relu)
            self.loss = tf.losses.mean_squared_error(labels=self.y, predictions=self.logits)
            self.lr_decay = tf.train.exponential_decay(self.learning_rate, self.global_step, 1000, 0.9, staircase=True)
            self.extra_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            
            with tf.control_dependencies(self.extra_update_ops):
                self.adam = tf.train.AdamOptimizer(self.lr_decay).minimize(self.loss,
                                                                           global_step=self.global_step)
                self.sgd = tf.train.GradientDescentOptimizer(self.lr_decay).minimize(self.loss,
                                                                                     global_step=self.global_step)
                self.rms = tf.train.RMSPropOptimizer(self.lr_decay).minimize(self.loss,
                                                                             global_step=self.global_step)
                self.momentum = tf.train.MomentumOptimizer(self.lr_decay, momentum=0.9).minimize(self.loss,
                                                                                                 global_step=self.global_step)
            
            tf.summary.scalar("loss", self.loss)

        self.merged_summary_op = tf.summary.merge_all()
		
	
###### 데이터 불러오기, 학습하기
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

root_dir = ".\\input_data"
img_dir = "./input_data/figure/"
logs_path = os.path.join(root_dir, "graph")

df = pd.read_csv(os.path.join(root_dir, 'description.csv'), engine='python')
img = df.img_name.values
img = np.array([img_dir + x for x in img])

classification = True

batch_size = 64
epochs = 5

if classification is True:
   label = pd.cut(df['WVHT ft.y'], bins=[0, 5.2, 7.9, 100], labels=[0, 1, 2], include_lowest=True).values
else:
   label = df['WVHT ft.y'].values
   label = ((label - np.mean(label)) / np.std(label)).reshape(-1, 1)
   
idx = [i for i in range(len(label)) if label[i] !=1]

img = img[idx]
label = label[idx]


for i in range(len(label)):
    if label[i] == 2:
        label[i] = 1
		
		
# Tensorflow Dataset API
train_img_tensor, train_label_tensor, test_img_tensor, test_label_tensor, tr_idx, ts_idx = set_input(img, label)

train_imgs = tf.data.Dataset.from_tensor_slices((train_img_tensor, train_label_tensor))
test_imgs = tf.data.Dataset.from_tensor_slices((test_img_tensor, test_label_tensor))
infer_imgs = tf.data.Dataset.from_tensor_slices((test_img_tensor, test_label_tensor))

if classification is True:
    train_imgs = train_imgs.map(input_tensor).apply(tf.contrib.data.unbatch()).shuffle(buffer_size=100).apply(lambda x: make_batch(x)).batch(batch_size).repeat()
    test_imgs = test_imgs.map(input_tensor).apply(tf.contrib.data.unbatch()).shuffle(buffer_size=100).apply(lambda x: make_batch(x)).batch(batch_size).repeat()
    infer_imgs = infer_imgs.map(input_tensor).apply(tf.contrib.data.unbatch()).batch(batch_size)
else:
    train_imgs = train_imgs.map(input_tensor_regression).apply(tf.contrib.data.unbatch()).shuffle(buffer_size=100).apply(lambda x: make_batch(x)).batch(batch_size).repeat()
    test_imgs = test_imgs.map(input_tensor_regression).apply(tf.contrib.data.unbatch()).shuffle(buffer_size=100).apply(lambda x: make_batch(x)).batch(batch_size).repeat()
    infer_imgs = infer_imgs.map(input_tensor).apply(tf.contrib.data.unbatch()).batch(batch_size)

train_iterator = train_imgs.make_initializable_iterator()
test_iterator = test_imgs.make_initializable_iterator()
infer_iterator = infer_imgs.make_initializable_iterator()
handle = tf.placeholder(tf.string, shape=[])

iterator = tf.data.Iterator.from_string_handle(handle, train_imgs.output_types, train_imgs.output_shapes)
x, y = iterator.get_next()

# train class: [22789, 19659]
train_batches = 22789*2 // batch_size

model = VGG16(x, y, bn=True, classification=classification)

if classification is True:
    model_name = "vgg16_classification_cropX"
else:
    model_name = "vgg16_regression_cropX"
	
	
start_time = time.time()

config = tf.ConfigProto()
config.gpu_options.allow_growth = True


sess = tf.Session(config=config)
saver = tf.train.Saver()
sess.run(tf.global_variables_initializer())
train_handle = sess.run(train_iterator.string_handle())
test_handle = sess.run(test_iterator.string_handle())
infer_handle = sess.run(infer_iterator.string_handle())
train_writer = tf.summary.FileWriter(os.path.join(logs_path, model_name, 'train'), sess.graph)
test_writer = tf.summary.FileWriter(os.path.join(logs_path, model_name, 'test'))

LEARNING_RATE = 0.001
optimizer = model.rms

# Training

if classification is True:

    print("Training!")
    for i in range(epochs):
        print("-------{} Epoch--------".format(i + 1))
        sess.run(train_iterator.initializer)
        sess.run(test_iterator.initializer)
        for j in range(train_batches):
            summary, _, acc, loss_ = sess.run([model.merged_summary_op, optimizer, model.accuracy, model.loss],
                                              feed_dict={handle: train_handle, model.learning_rate: LEARNING_RATE})
            step = tf.train.global_step(sess, model.global_step)
            print("Training Iter : {}, Acc : {}, Loss : {:.4f}".format(step, acc, loss_))

            if j % 10 == 0:
                train_writer.add_summary(summary, step)
                summary, acc, loss_ = sess.run([model.merged_summary_op, model.accuracy, model.loss],
                                               feed_dict={handle: test_handle})
                print("Validation Iter : {}, Acc : {}, Loss : {:.4f}".format(step, acc, loss_))
                test_writer.add_summary(summary, step)

    print("-----------End of training-------------")

    end_time = time.time() - start_time
    print("{} seconds".format(end_time))

    saver.save(sess, os.path.join(logs_path, 'VGG16_classification_crop', model_name))

else:
    print("Training!")
    for i in range(epochs):
        print("-------{} Epoch--------".format(i + 1))
        sess.run(train_iterator.initializer)
        sess.run(test_iterator.initializer)
        for j in range(train_batches):
            summary, _, loss_ = sess.run([model.merged_summary_op, optimizer, model.loss],
                                         feed_dict={handle: train_handle, model.learning_rate: LEARNING_RATE})
            step = tf.train.global_step(sess, model.global_step)
            print("Training Iter : {}, Loss : {:.4f}".format(step, loss_))

            if j % 10 == 0:
                train_writer.add_summary(summary, step)
                summary, loss_ = sess.run([model.merged_summary_op, model.loss],
                                          feed_dict={handle: test_handle})
                print("Validation Iter : {}, Loss : {:.4f}".format(step, loss_))
                test_writer.add_summary(summary, step)

    print("-----------End of training-------------")

    end_time = time.time() - start_time
    print("{} seconds".format(end_time))

    saver.save(sess, os.path.join(logs_path, 'VGG16_regression_crop', model_name))

	
	
# Inference

sess.run(infer_iterator.initializer)
y_true, y_pred = sess.run([model.y, model.y_pred], feed_dict={handle:infer_handle})
i = 0

 
while True:
    try:
         tmp_true, tmp_pred = sess.run([model.y, model.y_pred], feed_dict={handle:infer_handle})
         y_true = np.concatenate((y_true, tmp_true))
         y_pred = np.concatenate((y_pred, tmp_pred))
         if i % 200 == 0:
             print(i)
         i += 1
    except:
         y_true = np.array([np.where(r==1)[0][0] for r in y_true])
         break

len(y_pred)


df2 = pd.DataFrame(data={'y_true':y_true, 'y_pred':y_pred} )
df2.to_csv("{}_pred.csv".format(model_name), encoding='utf-8', index=False)


cm = skm.confusion_matrix(y_true, y_pred)
acc = skm.accuracy_score(y_true, y_pred)  # Accuracy
print("Accuracy : {}".format(acc))

pd.DataFrame(cm).to_csv("{}_cm.csv".format(model_name), encoding='utf-8')

report = skm.precision_recall_fscore_support(y_true, y_pred)
out_dict = { "precision" :report[0].round(3), "recall" : report[1].round(3),"f1-score" : report[2].round(3),
             "BCR": np.sqrt(report[0]*report[1]).round(3)}

pd.DataFrame(out_dict).to_csv("{}_report.csv".format(model_name), encoding='utf-8')