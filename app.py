# -*- coding: utf-8 -*-
"""app.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1H16Kn4ZyoorqsrsKyVZEvb9XjjP9jx0K
"""

'''Importing the required libraries'''
from flask import Flask, jsonify, request, render_template
import numpy as np
import pandas as pd
#import sklearn.externals as joblib
import pickle
from sklearn import preprocessing

#from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split
from scipy.stats import kurtosis,skew
from sklearn.linear_model import LogisticRegression

from sklearn.metrics import classification_report, confusion_matrix
import sklearn.metrics as metrics 

import matplotlib.pyplot as plt
import seaborn as sns

import flask
import os.path

app=Flask(__name__)

allowedFileExts= {"csv"}

def checkFileExt(file):
    return '.' in file and file.rsplit('.', 1)[1].lower() in allowedFileExts

''' Task: Data pre-processing'''

def preProcessData(eegdata): #(eegdata, dgdata):
    print("Started - preprocessing")
    eegdata.SubjectID=eegdata.SubjectID.astype(int)
    eegdata.VideoID=eegdata.VideoID.astype(int)
    #eegdata.predefinedlabel=eegdata.predefinedlabel.astype(int)
    #eegdata['user-definedlabeln']=eegdata['user-definedlabeln'].astype(int)

    eegdata.rename(columns = {#'predefinedlabel':'TgtLabel', 'user-definedlabeln':'UsrTgtLabel',
                          'SubjectID':'SubjectId', 'VideoID':'VideoId'}, inplace = True)

    eegdata['SubVdId']=eegdata['SubjectId'].map(str)+'-'+eegdata['VideoId'].map(str)
    eegdata['TimeSecs']=eegdata.groupby(['SubjectId','VideoId']).cumcount()+1
    videoLength=eegdata[['SubjectId', 'VideoId']].value_counts().to_list()
    eegdata=eegdata[eegdata.TimeSecs<=112]
    #print("Number of rows in eegdata: ", len(eegdata))

    
    '''demodict={'age': 'Age', 'ethnicity_Bengali' : 'EthnicityBengali',
       'ethnicity_English' : 'EthnicityEnglish', 'ethnicity_Han Chinese' : 'EthnicityHanChinese', 
       'gender_F' : 'Female', 'gender_M' : 'Male', 'subject ID':'SubjectId'}
    dgdata.rename(columns=demodict, inplace=True)
    dgdata=pd.get_dummies(dgdata)
    print("Number of rows in dgdata: ", len(dgdata))'''

    return eegdata, videoLength #eegdata, dgdata, videoLength


'''Task - Create datasets for multiple event epochs - 4,5,6,7,8,9,10,12,15, for any secs segements.
Note - Ensure to pass the appropriate event segment paramater value - epochSize'''

def fftFeatures(signal, topValues):
    fft=np.fft.fft(signal) #Computes the FFT
    magSpect=np.round_(np.abs(fft),2) # Extracts the absolute part from the complex numbers
    
    sortMag=magSpect[np.argsort(magSpect)] #Sorts the magnitude
    uniMag=np.unique(sortMag)[-topValues:] #Extract top unique values 
    
    inter, indMag, indUni=np.intersect1d(magSpect,uniMag, return_indices=True) #Gets the timestep index at which these top values occured
    eventInd=np.flip(indMag) #np.sort(indMag) #old logic
    '''eventInd=list(range(len(indMag)))

    for n in range(len(indMag)):
        num=indMag[n]
        if num==0:
            eventInd[n]=0
        else:
            eventInd[n]=np.round(float(1/num),2)
    
    eventInd=np.flip(eventInd)'''

    return uniMag, eventInd #Returns the unique top Magnitudes and the respective timestep at which this event magnitude occured


def genStatFFTFeatures(dataSub, id, epochSize=15):
    #Initialize variables and data structures
    st=0
    end=len(dataSub)

    dat=[]
    lbl=[]
    #Process from the beginning to the end of the trial
    for e in [x for x in range(end) if x%epochSize==0]:
    
        '''Generate statistical features with the time segment attached as part of the new column generated 
        after every epochSize per Subject'''
        dataStat=dataSub[['SubVdId', 'Delta','Theta','Alpha1','Alpha2','Beta1','Beta2','Gamma1','Gamma2']][e:e+epochSize]
        dataStat=dataStat.groupby(['SubVdId']).agg(['mean','std','var','median','min','max', 'skew'])
        dataStat.columns = [''.join(str(i) for i in col) for col in dataStat.columns]
        nameIndex=e+epochSize
        dataStat.columns=[col+'_'+str(nameIndex) for col in dataStat.columns]
        lbl.append(dataStat.columns)
        dat.append(dataStat.values)

    #Create a dataframe by combining the generated column names and statistical features
    result=pd.DataFrame(data=np.concatenate(dat).ravel(), columns=['val'])
    result['rowIndex']=[item for elem in lbl for item in elem]

    magnitude, magnitudeInd=fftFeatures(dataSub['Raw'], topValues=50)
    mag=[]
    magInd=[]

    for m in range(0,len(magnitude)):
        colMag='FFTMag_'+str(m)
        mag.append(colMag)

    for i in range(0,len(magnitudeInd)):
        colMagInd='EventMag_'+str(i)
        magInd.append(colMagInd)
    
    dictKey=[*magnitude, *magnitudeInd]
    dictVal=[*mag, *magInd]
    magDict={'val':dictKey, 'rowIndex':dictVal} #magDict={'val':magnitude, 'colnm':mag}
    fftDf=pd.DataFrame(magDict)
    result=result.append(fftDf)
      
    result=pd.pivot_table(result, columns='rowIndex', values='val')
    return result



#Input data preparation
def genFeatures(inpdata):
    eegFeatureSet=pd.DataFrame()
    svId=inpdata['SubVdId'].unique()
    magDict={}

    '''Loop through to generate features for all the Subjects.
    Remember to pass the appropriate epochSize here in the function call'''
    for s in svId:
        svDf=inpdata[inpdata['SubVdId']==s]
        eegFeatureSet=eegFeatureSet.append(genStatFFTFeatures(dataSub=svDf, id=s, epochSize=15))

    '''Create row index for easier identification of the subject combinations.
    The videos presented to subjects are of varying length. 
    Hence for certain shorter video id combinations like 120secs certain features at 140 secs cannot be generated.
    Substitute that with median of the respective feature (not 0) else compute the statistical features till 140+secs'''
    eegFeatureSet.index=inpdata['SubVdId'].unique()


    for n in eegFeatureSet.columns[eegFeatureSet.isnull().any(axis=0)]:
        eegFeatureSet[n].fillna(eegFeatureSet[n].median(),inplace=True)
    
    #eegFeatureSet=eegFeatureSet.replace(np.nan,0)

    #eegFeatureSet=np.log(eegFeatureSet)
    return eegFeatureSet

def addFeatures(inpdata1, inpdata3): #(inpdata1, inpdata2, inpdata3)
    inpdata1['SubjectId']=(inpdata1.index.str.slice(0,1)).astype(int)
    #inpdata1 = inpdata1.merge(inpdata2, on='SubjectId', how="inner").set_axis(inpdata1.index)
    inpdata1['VideoLen']=inpdata3
    return inpdata1

def dataScaling(inputdata1, scaler):
    '''Task - function to apply scaler that was fit on train data'''
    cols=inputdata1.columns

    output=pd.DataFrame(scaler.transform(inputdata1))
    output.columns=cols

    #y=inpdata2[["SubVdId", "UsrTgtLabel"]].groupby("SubVdId").first()
    #output["TgtLabel"]=y.UsrTgtLabel.to_list()
    output.index=inputdata1.index.to_list()

    return output




#Create a welcome page
@app.route('/', methods=['GET'])
def welcomePage():
    #return "Hello.. you have visited the page, <h1>Declutter-The Clutter!</h1>"
    return flask.render_template('info.html')

#Page on which the file upload form is loaded
@app.route('/index')
def index():
    return flask.render_template('index1.html')


#After file upload the predict function processes the file and generates results
@app.route('/predict', methods=['POST', 'GET'])
def predict():

    #Set to default values
    error=None 
    message=None
    combinations=None

    '''After file upload basic validations are performed before processing.
    Note - not processing the Student Demographics file as they are not the important features'''
    if request.method=='POST':
        if 'eegfile' not in request.files: #or 'dgfile' not in request.files:
            error='File is not yet uploaded!'
            return render_template('index1.html', error=error)	  


        eegfile=request.files['eegfile']
        eegfile_path="./data/" + eegfile.filename

        #dgfile=request.files['dgfile']
        #dgfile_path="./data/" + dgfile.filename

        if eegfile.filename=='': #or dgfile.filename=='':
            error="Choose the file before clicking on Upload."
            return render_template('index1.html', error=error)

        if eegfile.filename!='eegfile':
            error="Please provide appropriate file name and upload."
            return render_template('index1.html', error=error)

        '''if eegfile.filename==dgfile.filename:
            error="Duplicate files uploaded, cannot process the data."
            return render_template('index1.html', error=error)'''

        if checkFileExt(eegfile.filename)==False: #or checkFileExt(dgfile.filename)==False:
            error="Incorrect file type uploaded. Please upload the file with a .csv extension."
            return render_template('index1.html', error=error)

        eegfile.save(eegfile_path)
        #dgfile.save(dgfile_path)


        if((os.path.exists('./data/eegfile.csv')==False)): #or (os.path.exists('./data/dgfile.csv')==False)):
            error="Cannot process as the required input file is not uploaded."
            return render_template('index1.html', error=error)  
    
        #Load the trained model from pickle file
        modelFile=pickle.load(open('./model.pkl', 'rb'))

        file1=pd.read_csv('./data/eegfile.csv')
        #file2=pd.read_csv('./data/dgfile.csv')

        eegColumns=['SubjectID', 'VideoID', 'Attention', 'Mediation', 'Raw', 'Delta', 'Theta', 'Alpha1', 'Alpha2',
                    'Beta1', 'Beta2', 'Gamma1', 'Gamma2'] #, 'predefinedlabel', 'user-definedlabeln']

        #dgColumns=['subject ID', 'age', 'ethnicity', 'gender']

        #Remove the leading/trialing spaces in column names
        file1=file1.rename(columns=lambda r: r.strip())
        #file2=file2.rename(columns=lambda r: r.strip())
        file1Columns=file1.columns.to_list()
        #file2Columns=file2.columns.to_list()
        

        '''Verfies the file content'''
        
        if (file1.columns.to_list()==eegColumns):
            eegData=file1
        else:
            error="Incorrect column names. Upload the correct file."
            return render_template('index1.html', error=error)

        '''if (file1.columns.to_list()==dgColumns):
            dgInfo=file1
        if (file2.columns.to_list()==eegColumns):
            eegData=file2
        if (file2.columns.to_list()==dgColumns):
            dgInfo=file2'''

        #Basic checks on files uploaded before the data is processed
        if ((len(eegData)==0)): # or (len(dgInfo)==0)):
            error="The EEG file has no data to process."
            return render_template('index1.html', error=error)

        '''if (eegData.equals(dgInfo)):
            error="Cannot process EEG data as duplicate csv files have been uploaded." '''
        if (len(eegData)<75): #At over all EEG file level
            error="Cannot process EEG data as a minimum of 75 timesteps is required."
            return render_template('index1.html', error=error)

        if ((eegData.isnull().values.any()==True) or (eegData.isnull().sum().sum()!=0) or (np.isinf(eegData).values.sum()!=0)):
            error="Cannot process EEG data as NULLs or NAs or infs are present" 
            return render_template('index1.html', error=error)


        '''Ensures that a minimum of 75 timesteps are present for each Subject-VideoId
        combination. Only those Subject-VideoId combinations are processed that meet 
        this criteria. For combinations that donot meet are not processed and a message
        summary is provided at the end of the processing'''
        eegCounts=pd.DataFrame(eegData[['SubjectID', 'VideoID']].value_counts()>=75)
        if (len(eegCounts)==0):
            error="Cannot process the EEG data as the Subject-VideoId combinations have timesteps<75"
            return render_template('index1.html', error=error)
        else:
            eegData=eegData.merge(eegCounts[eegCounts[0]==True], on=['SubjectID', 'VideoID'], how='inner')
            notProcessed=eegCounts[eegCounts[0]==False].index.to_frame(index=False)


            #Adds video length as another feature
            eegData, videoLength = preProcessData(eegData)

            #eegData, dgInfo, videoLength = preProcessData(eegData, dgInfo)

            eegFeatureSet=genFeatures(eegData)
            #eegFeatureSet=addFeatures(eegFeatureSet, dgInfo, videoLength)
            eegFeatureSet=addFeatures(eegFeatureSet, videoLength)

            
    
            #Variables from pickle file
            model=modelFile[2]
            features=modelFile[0]

            #Scale the query datapoint
            eegScaled=dataScaling(eegFeatureSet[features], modelFile[1]) 
          
            #Stores processed query data point
            Xtest=eegScaled
            #ytest=eegScaled.TgtLabel.to_list()

            #Predicts on the query data point
            yhat=model.predict(Xtest)
            yhat_probabilities=model.predict_proba(Xtest)
        
            #Generates the output
            prediction=['Confused' if result==1 else 'Not Confused' for result in yhat]
    
            results=[]
            for i in range(len(prediction)):
                results.append("The Student-VideoId combination "+str(Xtest.index[i])+" is predicted as "+str(prediction[i])+" with a probability of: "+str("%.3f" %(yhat_probabilities[i,yhat[i]])))

            #Apart from predictions if any unprocessed subjects (<75 timesteps) are reported
            if(len(notProcessed)!=0):
                combinations=list(notProcessed['SubjectID'].map(str)+'-'+notProcessed['VideoID'].map(str))      

    return flask.render_template("message.html", results=results, combinations=combinations)
    #notProcessed['SubjectID'].map(str)+'-'+notProcessed['VideoID'].map(str)


if __name__=='__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
