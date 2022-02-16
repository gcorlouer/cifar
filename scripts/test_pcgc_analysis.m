%% Testing validity of single trial gc analysis

input_parameters;
subject = 'DiAs';
condition = {'Rest', 'Face', 'Place', 'baseline'};
field = {'time',  'condition', 'pair', 'subject','F'};
dataset = struct;
%% Load data

datadir = fullfile('~', 'projects', 'cifar', 'results');

%%

fname = [subject '_condition_visual_ts.mat'];
fpath = fullfile(datadir, fname);

% Meta data about time series
time_series = load(fpath);
time = time_series.time; fs = double(time_series.sfreq);

% Functional group indices
indices = time_series.indices; fn = fieldnames(indices);

% Read conditions specific time series
c = 2;
X = time_series.(condition{c});
time = time_series.time;
[n, m, N] = size(X);

%% Test detrending

pdeg = 2;
mX = mean(X,1);
[dX,~,~,~] = mvdetrend(X,pdeg,[]);
mdX = mean(dX,1);
k = 5;
subplot(2,1,1)
plot(time, mX(1,:,k))
title('No detrend')
subplot(2,1,2)
plot(time, mdX(1,:,k))
title(['Detrend of deg ' num2str(pdeg)])
%%
