import os
import argparse
import yaml
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from IPython.core.debugger import Pdb

from preprocess import preprocess
from dataset import VQADataset, VQABatchSampler
from train import train_model
from vqa import VQAModel
from san import SANModel
from scheduler import CustomReduceLROnPlateau

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', type=str, default='config.yml')


def load_datasets(config, phases):
    config = config['data']
    if 'preprocess' in config and config['preprocess']:
        print('Preprocessing datasets')
        preprocess(
            data_dir=config['dir'],
            train_ques_file=config['train']['ques'],
            train_ans_file=config['train']['ans'],
            val_ques_file=config['val']['ques'],
            val_ans_file=config['val']['ans'])

    print('Loading preprocessed datasets')
    datafiles = {x: '{}.pkl'.format(x) for x in phases}
    raw_images = 'preprocess' in config['images'] and config['images']['preprocess']
    if raw_images:
        img_dir = {x: config[x]['img_dir'] for x in phases}
    else:
        img_dir = {x: config[x]['emb_dir'] for x in phases}
    datasets = {x: VQADataset(data_dir=config['dir'], qafile=datafiles[x], img_dir=img_dir[x], phase=x, img_scale=config['images']['scale'], img_crop=config['images']['crop'], raw_images=raw_images) for x in phases}
    batch_samplers = {x: VQABatchSampler(datasets[x], 32) for x in phases}

    dataloaders = {x: DataLoader(datasets[x], batch_sampler=batch_samplers[x], num_workers=config['loader']['workers']) for x in phases}
    dataset_sizes = {x: len(datasets[x]) for x in phases}
    print(dataset_sizes)
    print("ques vocab size: {}".format(len(VQADataset.ques_vocab)))
    print("ans vocab size: {}".format(len(VQADataset.ans_vocab)))
    return dataloaders, VQADataset.ques_vocab, VQADataset.ans_vocab


def main(config):
    phases = ['train', 'val']
    dataloaders, ques_vocab, ans_vocab = load_datasets(config, phases)
    config['model']['params']['vocab_size'] = len(ques_vocab)
    config['model']['params']['output_size'] = len(ans_vocab) - 1       # don't want model to predict '<unk>'

    if config['model_class'] == 'vqa':
        model = VQAModel(**config['model']['params'])
    elif config['model_class'] == 'san':
        model = SANModel(**config['model']['params'])
    print(model)
    criterion = nn.CrossEntropyLoss()

    if config['optim']['class'] == 'sgd':
        optimizer = optim.SGD(filter(lambda p: p.requires_grad, model.parameters()),
                              **config['optim']['params'])
    elif config['optim']['class'] == 'rmsprop':
        optimizer = optim.RMSprop(filter(lambda p: p.requires_grad, model.parameters()),
                                  **config['optim']['params'])
    else:
        optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()),
                               **config['optim']['params'])



    #
    best_acc = 0
    Pdb().set_trace()
    if ((config['training']['start_from_checkpoint'])):
        pathForTrainedModel = os.path.join(config['save_dir'],config['checkpoints']['path'])
        if os.path.exists(pathForTrainedModel):
            print("=> loading checkpoint/model found at '{0}'".format(pathForTrainedModel))
            checkpoint = torch.load(pathForTrainedModel)
            startEpoch = checkpoint['epoch']
            model.load_state_dict(checkpoint['state_dict'])
            #optimizer.load_state_dict(checkpoint['optimizer'])




    if config['use_gpu']:
            model = model.cuda()
    
    if 'scheduler' in config['optim'] and config['optim']['scheduler'].lower() == 'CustomReduceLROnPlateau'.lower():
        print('CustomReduceLROnPlateau')
        exp_lr_scheduler = CustomReduceLROnPlateau(optimizer, config['optim']['scheduler_params']['maxPatienceToStopTraining'], config['optim']['scheduler_params']['base_class_params'])
    else:
        # Decay LR by a factor of gamma every step_size epochs
        print('lr_scheduler.StepLR')
        exp_lr_scheduler = lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.1)


    print("begin training")
    save_dir = os.path.join(os.getcwd(),config['save_dir'])
    model = train_model(model, dataloaders, criterion, optimizer, exp_lr_scheduler, save_dir,
                        num_epochs=config['training']['no_of_epochs'], use_gpu=config['use_gpu'], best_accuracy=best_acc)


if __name__ == '__main__':
    global args
    args = parser.parse_args()
    args.config = os.path.join(os.getcwd(), args.config)
    config = yaml.load(open(args.config))
    config['use_gpu'] = config['use_gpu'] and torch.cuda.is_available()

    # TODO: seeding still not perfect
    torch.manual_seed(config['seed'])
    torch.cuda.manual_seed(config['seed'])
    main(config)
