
import os
import glob
import torch
from results import Results
from itertools import islice
from datetime import datetime 
from torch.autograd import Variable


def avoidWarnings():
    import warnings
    warnings.filterwarnings('always')
    warnings.filterwarnings('ignore')
    warnings.filterwarnings('ignore', 'ImportWarning')
    warnings.filterwarnings('ignore', 'DeprecationWarning')   
    
    
now = datetime.now
def time(start):
    ''' Helper function to track time wrt an anchor'''
    elapsed = (now() - start).total_seconds()
    hours =  int(elapsed/3600)
    minutes = round((elapsed/3600 - hours)*60, 2)
    return hours, minutes


def print_stats(epoch, epochs, j, iters, lss, acc, subset, n=None):
    if n:
        stat = [subset, n, epoch, epochs, j, iters, lss, acc]        
        stats = '\n {} Model {}: Epoch: [{}/{}] Iter: [{}/{}] Loss: {} Acc: {}%'.format(*stat)
    else:
        stat = [subset, epoch, epochs, j, iters, lss, acc]        
        stats = '\n {} Ensemble: Epoch: [{}/{}] Iter: [{}/{}] Loss: {} Acc: {}%'.format(*stat)
    print(stats)    
    
    
def train(dataset, names, models, optimizers, criterion, device, trainloader, validloader,
          epochs, iters, save, paths, save_frequency=1, test=True, validate=True):
    
    com_iter = True
    com_epoch = True
    # Every model train mode
    for m in models: m.train()
            
    # Initialize results
    j = 0 
    timer = []
    best_acc = 0
    results = Results(models)
    len_ = len(trainloader)
    
    avoidWarnings()
    modelpath = paths['models']

    # Testing mode
    if test:         
        epochs = 5
        print('training in test mode')
        trainloader = islice(trainloader, 20)
        validloader = islice(validloader, 20)
#        len_ = 2
            
    start = now()
    for epoch in range(1, epochs+1):
                
        # Training
        # --------
        for i, (images, labels) in enumerate(trainloader):
            
            j += 1 # for printing
            images = Variable(images)
            labels = Variable(labels)
            
            images = images.to(device)
            labels = labels.to(device)
            
            outputs = []
            for n, m in enumerate(models):
                
                # Scheduler for learning rate        
                if (j == 32000 or j == 48000):  
                    for p in optimizers[n].param_groups: p['lr'] = p['lr'] / 10

                ## Individual forward pass
                
                # Calculate loss for individual                
                m.zero_grad()
                output = m(images)
                outputs.append(output)
                loss = criterion(output, labels) 
                
                # Calculate accy for individual
                _, predictions = torch.max(output.data, 1)
                correct, total = 0, 0
                total += output.size(0)
                correct += int(sum(predictions == labels)) 
                accuracy = correct / total
                                
                lss = round(loss.item(), 3)
                acc = round(accuracy * 100, 2)
            
                # Store iteration results for this individual
                results.append_iter_loss(lss, 'train', n+1)
                results.append_iter_accy(acc, 'train', n+1)
                
                if i == len_-1:
                    # Store epoch results for this individual (as last iter)
                    results.append_loss(lss, 'train', n+1)
                    results.append_accy(acc, 'train', n+1)
                    
                if com_iter: print_stats(epoch, epochs, j, iters, lss, acc, 'Train', n+1)  
                
                # Individual backwad pass                           # How does loss.backward wicho model is?
                
                loss.backward()
                optimizers[n].step()        
                
                
            ## Ensemble foward pass
            
            outputs = torch.mean(torch.stack(outputs), dim=0)
            
            # Calculate loss for ensemble
            loss = criterion(output, labels) 
            correct, total = 0, 0 
            
            # Calculate accuracy for ensemble
            _, preds = outputs.max(1)
            total += outputs.size(0)
            correct += int(sum(preds == labels))
            
            lss = round(loss.item(), 3)
            acc = round(accuracy * 100, 2)
            
            # Store iteration results for Ensemble
            results.append_iter_loss(lss, 'train', None)
            results.append_iter_accy(acc, 'train', None)
            
            # Print results
            if com_iter: print_stats(epoch, epochs, j, iters, lss, acc, 'Train')
        
        # Store epoch results for Ensemble
        results.append_loss(lss, 'train', None)
        results.append_accy(acc, 'train', None)
                
        # Print results
        if com_epoch: print_stats(epoch, epochs, j, iters, lss, acc, 'Train')
            
        # Validation
        # ----------
        if validate:
            
            for k, (images, labels) in enumerate(validloader):
            
                images = Variable(images)
                labels = Variable(labels)
                
                images = images.to(device)
                labels = labels.to(device)
                
                outputs = []
                for n, m in enumerate(models):
                    
                    ## Individuals foward pass
            
                    m.zero_grad()
                    output = m(images)
                    outputs.append(output)
                                        
                    # Store epoch results for each model
                    if k == 0:
                        
                        loss = criterion(output, labels) 
                    
                        correct, total = 0, 0
                        _, predictions = torch.max(output.data, 1)
                        total += output.size(0)
                        correct += int(sum(predictions == labels)) 
                        accuracy = correct / total
                                        
                        lss = round(loss.item(), 3)
                        acc = round(accuracy * 100, 2)
                    
                        results.append_loss(lss, 'valid', n+1)
                        results.append_accy(acc, 'valid', n+1)
                        
                        if com_epoch: 
                            print_stats(epoch, epochs, j, iters, lss, acc, 'Valid', n+1)
                    
                ## Ensemble foward pass
                
                outputs = torch.mean(torch.stack(outputs), dim=0)
                    
                loss = criterion(outputs, labels)  
                
                correct, total = 0, 0
                _, preds = outputs.max(1)
                total += outputs.size(0)
                correct += int(sum(preds == labels))
                
            accuracy = correct / total
            lss = round(loss.item(), 3)
            acc = round(accuracy * 100, 2)
            
            # Store epoch results for Ensemble
            results.append_loss(lss, 'valid', None)
            results.append_accy(acc, 'valid', None)
            
            # Print results
            if com_epoch: print_stats(epoch, epochs, j, iters, lss, acc, 'Valid', n+1)
                
            # Save model and delete previous if it is the best
            if acc > best_acc:
                
                prev_models = glob.glob(os.path.join(modelpath, '*.pkl'))
                for p in prev_models:
                    os.remove(p)
                    
                for i, m in enumerate(models):                    
                    torch.save(m.state_dict(), os.path.join(modelpath, '%s-%d.pkl' % (names[i], epoch))) 
                best_acc = acc
                    
        timer.append(time(start))
        
    return results, timer
