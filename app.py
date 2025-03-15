import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
class GateIOSwingTradeScanner:
    def __init__(self):
        load_dotenv()
        self.api_key=os.getenv('GATEIO_API_KEY')
        self.secret_key=os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:raise ValueError("API keys missing")
        config=Configuration(key=self.api_key,secret=self.secret_key,host="https://api.gateio.ws/api/v4")
        self.client=ApiClient(config)
        self.futures_api=FuturesApi(self.client)
        self.leverage=5
        self.order_amount=50
        self.lookback_period=100
        self.devlen=2.0
    def get_futures_contracts(self)->List[str]:
        ticket=self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts=[]
        pattern=re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT','DOGS_USDT']:
                json_data=contract.to_dict()
                if float(json_data['volume_24h'])*float(json_data['last'])>500000:
                    valid_contracts.append(contract.contract)
        print(f"พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา",flush=True)
        return valid_contracts
    def get_candlesticks(self,contract:str)->pd.DataFrame:
        candles=self.futures_api.list_futures_candlesticks(settle='usdt',contract=contract,interval='15m',limit=500)
        if not candles:return pd.DataFrame()
        data=[{'timestamp':float(c.t),'open':float(c.o),'high':float(c.h),'low':float(c.l),'close':float(c.c),'volume':float(c.v)} for c in candles]
        df=pd.DataFrame(data)
        df['timestamp']=pd.to_datetime(df['timestamp'],unit='s')
        return df.sort_values('timestamp')
    def calculate_linear_regression_channel(self,df:pd.DataFrame)->pd.DataFrame:
        if len(df)<self.lookback_period:return pd.DataFrame()
        x=np.arange(self.lookback_period)
        df['mid']=df['close'].rolling(self.lookback_period).apply(lambda y:np.polyfit(x,y,1)[1]+np.polyfit(x,y,1)[0]*x[-1],raw=True)
        df['dev']=df['close'].rolling(self.lookback_period).apply(lambda y:np.std(y-np.polyval(np.polyfit(x,y,1),x)),raw=True)
        df['TOP']=df['mid']+df['dev']*self.devlen
        df['BOTTOM']=df['mid']-df['dev']*self.devlen
        df['MIDDLE']=df['mid']
        print(f"คำนวณ Linear Regression Channel: TOP={df.iloc[-1]['TOP']:.6f}, BOTTOM={df.iloc[-1]['BOTTOM']:.6f}, MIDDLE={df.iloc[-1]['MIDDLE']:.6f}",flush=True)
        return df.dropna()
    def check_trading_signal(self,df:pd.DataFrame)->str:
        if len(df)<1:return None
        candle=df.iloc[-1]
        is_green=candle['close']>candle['open']
        is_red=candle['close']<candle['open']
        high_above_top=candle['high']>candle['TOP']
        low_below_bottom=candle['low']<candle['BOTTOM']
        if is_green and high_above_top:
            print(f"สัญญาณ BUY: CANDLE สีเขียว (close={candle['close']:.6f} > open={candle['open']:.6f}) และ high={candle['high']:.6f} > TOP={candle['TOP']:.6f}",flush=True)
            return "BUY"
        elif is_red and low_below_bottom:
            print(f"สัญญาณ SELL: CANDLE สีแดง (close={candle['close']:.6f} < open={candle['open']:.6f}) และ low={candle['low']:.6f} < BOTTOM={candle['BOTTOM']:.6f}",flush=True)
            return "SELL"
        return None
    def set_leverage(self,contract:str)->bool:
        try:
            self.futures_api.update_position_leverage(contract=contract,settle='usdt',leverage=str(self.leverage))
            print(f"ตั้งค่า leverage {self.leverage}x สำหรับ {contract}",flush=True)
            return True
        except Exception as e:
            print(f"ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}",flush=True)
            return False
    def get_latest_price(self,contract:str)->float:
        ticker=self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract==contract:return float(t.last)
        print(f"ไม่พบราคาสำหรับ {contract}",flush=True)
        return None
    def check_existing_position(self,contract:str)->Dict:
        positions=self.futures_api.list_positions(settle='usdt',holding=True)
        for p in positions:
            if p.contract==contract:
                position_info=p.to_dict()
                size=float(position_info['size'])
                position_type="LONG" if size>0 else "SHORT" if size<0 else "NONE"
                print(f"พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}",flush=True)
                return position_info
        return None
    def close_position(self,contract:str,position:Dict)->bool:
        try:
            size=float(position['size'])
            if size!=0:
                direction=abs(size) if size<0 else -size
                self.futures_api.create_futures_order('usdt',{'contract':contract,'size':direction,'price':0,'tif':'ioc','reduce_only':True})
                position_type="LONG" if size>0 else "SHORT"
                print(f"ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}",flush=True)
                return True
            return False
        except Exception as e:
            print(f"ไม่สามารถปิด position สำหรับ {contract}: {str(e)}",flush=True)
            return False
    def create_long_order(self,contract:str)->Dict:
        try:
            if not self.set_leverage(contract):return None
            price=self.get_latest_price(contract)
            if not price:return None
            contract_info=self.futures_api.get_futures_contract(contract=contract,settle='usdt')
            multiplier=float(contract_info.to_dict()['quanto_multiplier'])
            min_size=float(contract_info.to_dict()['order_size_min'])
            usd_value=self.order_amount*self.leverage
            size=max(min_size,round(usd_value/(price*multiplier)))
            order=self.futures_api.create_futures_order('usdt',{'contract':contract,'size':size,'price':0,'tif':'ioc','reduce_only':False})
            print(f"เปิด position LONG: {contract} ขนาด={size}",flush=True)
            return order
        except Exception as e:
            print(f"ไม่สามารถเปิด LONG สำหรับ {contract}: {str(e)}",flush=True)
            return None
    def create_short_order(self,contract:str)->Dict:
        try:
            if not self.set_leverage(contract):return None
            price=self.get_latest_price(contract)
            if not price:return None
            contract_info=self.futures_api.get_futures_contract(contract=contract,settle='usdt')
            multiplier=float(contract_info.to_dict()['quanto_multiplier'])
            min_size=float(contract_info.to_dict()['order_size_min'])
            usd_value=self.order_amount*self.leverage
            size=max(min_size,round(usd_value/(price*multiplier)))
            order=self.futures_api.create_futures_order('usdt',{'contract':contract,'size':-size,'price':0,'tif':'ioc','reduce_only':False})
            print(f"เปิด position SHORT: {contract} ขนาด={size}",flush=True)
            return order
        except Exception as e:
            print(f"ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}",flush=True)
            return None
    def scan_positions(self):
        try:
            positions=[p.to_dict() for p in self.futures_api.list_positions(settle='usdt',holding=True)]
            print(f"สแกน {len(positions)} positions ที่เปิดอยู่",flush=True)
            for pos in positions:
                contract=pos['contract']
                df=self.get_candlesticks(contract)
                if not df.empty:
                    df=self.calculate_linear_regression_channel(df)
                    if df.empty:continue
                    latest_price=self.get_latest_price(contract)
                    if not latest_price:continue
                    middle=df.iloc[-1]['MIDDLE']
                    size=float(pos['size'])
                    if size>0 and latest_price<middle:
                        print(f"ปิด LONG position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} < MIDDLE={middle:.6f}",flush=True)
                        self.close_position(contract,pos)
                    elif size<0 and latest_price>middle:
                        print(f"ปิด SHORT position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} > MIDDLE={middle:.6f}",flush=True)
                        self.close_position(contract,pos)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน positions: {str(e)}",flush=True)
    def scan_market(self):
        first_run=True
        while True:
            current_time=pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute%15==0 or first_run:
                print(f"เริ่มสแกนตลาด ณ เวลา {current_time}",flush=True)
                first_run=False
                self.scan_positions()
                contracts=self.get_futures_contracts()
                for contract in contracts:
                    df=self.get_candlesticks(contract)
                    if df.empty:continue
                    df=self.calculate_linear_regression_channel(df)
                    if df.empty:continue
                    signal=self.check_trading_signal(df)
                    existing_pos=self.check_existing_position(contract)
                    if signal=="BUY":
                        if existing_pos and float(existing_pos['size'])<0:
                            if self.close_position(contract,existing_pos):
                                self.create_long_order(contract)
                        elif not existing_pos:
                            self.create_long_order(contract)
                    elif signal=="SELL":
                        if existing_pos and float(existing_pos['size'])>0:
                            if self.close_position(contract,existing_pos):
                                self.create_short_order(contract)
                        elif not existing_pos:
                            self.create_short_order(contract)
                time.sleep(30)
            time.sleep(10)
def main():
    scanner=GateIOSwingTradeScanner()
    print("เริ่มต้นระบบสแกนตลาด Futures ด้วย Linear Regression Channel...",flush=True)
    scanner.scan_market()
if __name__=="__main__":
    main()