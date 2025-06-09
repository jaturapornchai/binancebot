#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import logging, json
from rich.table import Table

class DisplayManager:
    def __init__(self):
        self.logger = logging.getLogger("AltcoinMomentumScanner")
    
    def display_scan_summary(self, results, duration, cache, console, terms, advice, fibo_names):
        """แสดงผลสรุปการสแกนเหรียญ"""
        try:
            scan_time = cache['last_scan'].strftime('%Y-%m-%d %H:%M:%S')
            summary_table = Table(title=f"ผลการสแกนโมเมนตัม Altcoin - {scan_time}")
            summary_table.add_column("สัญญาณ", style="cyan")
            summary_table.add_column("จำนวน", style="yellow")
            summary_table.add_column("คำอธิบาย", style="white")
            
            counts = {s: len(results[s]) for s in results}
            total = sum(counts.values())
            
            btc_analysis = cache['btc_analysis']
            btc_primary = btc_analysis.get('primary', {})
            btc_trend = btc_primary.get('trend', 'NEUTRAL')
            btc_signal = btc_primary.get('signal', 'CONSOLIDATION')
            btc_score = btc_primary.get('momentum_score', 0)
            btc_score_10 = btc_primary.get('score_10', 0)
            
            btc_trend_color = "green" if btc_trend == 'UPTREND' else "red" if btc_trend == 'DOWNTREND' else "yellow"
            btc_signal_term = terms.get(btc_signal, 'กำลังสะสม')
            btc_signal_color = "green" if "BREAKOUT" in btc_signal else "red" if "BREAKDOWN" in btc_signal else "yellow"
            
            summary_table.add_row(
                f"[bold]BTC: {btc_analysis['1h']['price']:.0f}$[/bold]", 
                f"[{btc_trend_color}]{btc_trend}[/{btc_trend_color}]", 
                f"[{btc_signal_color}]{btc_signal_term}[/{btc_signal_color}] (คะแนน: {btc_score_10:.1f}/10)"
            )
            
            summary_table.add_row(terms['STRONG_BREAKOUT'], f"{counts['STRONG_BREAKOUT']}", advice['STRONG_BREAKOUT'])
            summary_table.add_row(terms['BREAKOUT'], f"{counts['BREAKOUT']}", advice['BREAKOUT'])
            summary_table.add_row(terms['BREAKDOWN'], f"{counts['BREAKDOWN']}", advice['BREAKDOWN'])
            summary_table.add_row(terms['STRONG_BREAKDOWN'], f"{counts['STRONG_BREAKDOWN']}", advice['STRONG_BREAKDOWN'])
            summary_table.add_row(terms['CONSOLIDATION'], f"{counts['CONSOLIDATION']}", advice['CONSOLIDATION'])
            summary_table.add_row("📊 รวมทั้งหมด", f"{total}", f"ใช้เวลาวิเคราะห์ {duration:.1f} วินาที")
            
            console.print("\n")
            console.print(summary_table)
            
            for signal in ['STRONG_BREAKOUT', 'BREAKOUT', 'STRONG_BREAKDOWN', 'BREAKDOWN']:
                coins = results[signal]
                if not coins: continue
                
                signal_text = terms[signal]
                signal_color = "green" if "BREAKOUT" in signal else "red"
                
                coin_table = Table(title=f"{signal_text}")
                coin_table.add_column("เหรียญ", style="cyan")
                coin_table.add_column("ราคา", style="yellow")
                coin_table.add_column("คะแนน", style="magenta")
                coin_table.add_column("Entry", style="green")
                coin_table.add_column("SL", style="red")
                coin_table.add_column("TP", style="blue")
                coin_table.add_column("R:R", style="magenta")
                coin_table.add_column("Fibo", style="cyan")
                coin_table.add_column("BTC Align", style="cyan")
                
                for coin in coins[:5]:
                    entry = coin.get('entry', coin['price'])
                    stop_loss = coin.get('stop_loss')
                    take_profit = coin.get('take_profit')
                    
                    if stop_loss and take_profit:
                        risk = abs(entry - stop_loss)
                        reward = abs(take_profit - entry)
                        rr_ratio = reward / risk if risk > 0 else 0
                        rr_display = f"{rr_ratio:.2f}:1"
                    else: 
                        rr_display = "-"
                    
                    fibo_support_level = coin.get('fibo_support_level')
                    fibo_resistance_level = coin.get('fibo_resistance_level')
                    fibo_display = ""
                    
                    if 'BREAKOUT' in signal and fibo_resistance_level is not None:
                        fibo_display = f"R:{fibo_names.get(fibo_resistance_level, str(fibo_resistance_level))}"
                    elif 'BREAKDOWN' in signal and fibo_support_level is not None:
                        fibo_display = f"S:{fibo_names.get(fibo_support_level, str(fibo_support_level))}"
                    
                    btc_aligned = coin.get('btc_aligned', False)
                    btc_corr = coin.get('btc_correlation', 0)
                    btc_align_display = f"[green]Yes[/green]" if btc_aligned else f"[red]No[/red]"
                    
                    if abs(btc_corr) > 0.7:
                        btc_align_display += f" ({btc_corr:.2f})"
                    
                    coin_table.add_row(
                        coin['symbol'],
                        f"{coin['price']:.6f}",
                        f"{coin['score_10']:.1f}/10",
                        f"{entry:.6f}" if entry else "-",
                        f"{stop_loss:.6f}" if stop_loss else "-",
                        f"{take_profit:.6f}" if take_profit else "-",
                        rr_display,
                        fibo_display,
                        btc_align_display
                    )
                
                console.print(coin_table)
                
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงผลสรุป: {str(e)}")
    
    def display_filtered_breakout(self, breakout_coins, terms, console, fibo_names, show_fibo=False):
        """แสดงเหรียญที่มีสัญญาณ breakout"""
        try:
            table = Table(title=f"เหรียญที่มีสัญญาณ {terms['BREAKOUT']} ({len(breakout_coins)} เหรียญ)")
            table.add_column("เหรียญ", style="cyan")
            table.add_column("ราคา", style="yellow")
            table.add_column("คะแนน", style="green")
            table.add_column("Entry", style="green")
            table.add_column("SL", style="red")
            table.add_column("TP", style="blue")
            table.add_column("R:R", style="magenta")
            
            if show_fibo:
                table.add_column("Fibo", style="cyan")
                
            table.add_column("BTC Align", style="cyan")
            
            for coin in breakout_coins[:15]:
                entry = coin.get('entry', coin['price'])
                stop_loss = coin.get('stop_loss')
                take_profit = coin.get('take_profit')
                
                if stop_loss and take_profit:
                    risk = abs(entry - stop_loss)
                    reward = abs(take_profit - entry)
                    rr_ratio = reward / risk if risk > 0 else 0
                    rr_display = f"{rr_ratio:.2f}:1"
                else: 
                    rr_display = "-"
                
                fibo_display = ""
                if show_fibo:
                    fibo_resistance_level = coin.get('fibo_resistance_level')
                    if fibo_resistance_level is not None:
                        fibo_display = f"R:{fibo_names.get(fibo_resistance_level, str(fibo_resistance_level))}"
                
                btc_aligned = coin.get('btc_aligned', False)
                btc_corr = coin.get('btc_correlation', 0)
                btc_align_display = f"[green]Yes[/green]" if btc_aligned else f"[red]No[/red]"
                
                if abs(btc_corr) > 0.7:
                    btc_align_display += f" ({btc_corr:.2f})"
                
                row_data = [
                    coin['symbol'],
                    f"{coin['price']:.6f}",
                    f"{coin['score_10']:.1f}/10",
                    f"{entry:.6f}" if entry else "-",
                    f"{stop_loss:.6f}" if stop_loss else "-",
                    f"{take_profit:.6f}" if take_profit else "-",
                    rr_display
                ]
                
                if show_fibo:
                    row_data.append(fibo_display)
                    
                row_data.append(btc_align_display)
                table.add_row(*row_data)
                
            console.print(table)
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงเหรียญ breakout: {str(e)}")
    
    def display_filtered_breakdown(self, breakdown_coins, terms, console, fibo_names, show_fibo=False):
        """แสดงเหรียญที่มีสัญญาณ breakdown"""
        try:
            table = Table(title=f"เหรียญที่มีสัญญาณ {terms['BREAKDOWN']} ({len(breakdown_coins)} เหรียญ)")
            table.add_column("เหรียญ", style="cyan")
            table.add_column("ราคา", style="yellow")
            table.add_column("คะแนน", style="red")
            table.add_column("Entry", style="green")
            table.add_column("SL", style="red")
            table.add_column("TP", style="blue")
            table.add_column("R:R", style="magenta")
            
            if show_fibo:
                table.add_column("Fibo", style="cyan")
                
            table.add_column("BTC Align", style="cyan")
            
            for coin in breakdown_coins[:15]:
                entry = coin.get('entry', coin['price'])
                stop_loss = coin.get('stop_loss')
                take_profit = coin.get('take_profit')
                
                if stop_loss and take_profit:
                    risk = abs(entry - stop_loss)
                    reward = abs(take_profit - entry)
                    rr_ratio = reward / risk if risk > 0 else 0
                    rr_display = f"{rr_ratio:.2f}:1"
                else: 
                    rr_display = "-"
                
                fibo_display = ""
                if show_fibo:
                    fibo_support_level = coin.get('fibo_support_level')
                    if fibo_support_level is not None:
                        fibo_display = f"S:{fibo_names.get(fibo_support_level, str(fibo_support_level))}"
                
                btc_aligned = coin.get('btc_aligned', False)
                btc_corr = coin.get('btc_correlation', 0)
                btc_align_display = f"[green]Yes[/green]" if btc_aligned else f"[red]No[/red]"
                
                if abs(btc_corr) > 0.7:
                    btc_align_display += f" ({btc_corr:.2f})"
                
                row_data = [
                    coin['symbol'],
                    f"{coin['price']:.6f}",
                    f"{coin['score_10']:.1f}/10",
                    f"{entry:.6f}" if entry else "-",
                    f"{stop_loss:.6f}" if stop_loss else "-",
                    f"{take_profit:.6f}" if take_profit else "-",
                    rr_display
                ]
                
                if show_fibo:
                    row_data.append(fibo_display)
                    
                row_data.append(btc_align_display)
                table.add_row(*row_data)
                
            console.print(table)
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงเหรียญ breakdown: {str(e)}")
    
    def display_coin_analysis(self, symbol, coin_data, btc_analysis, console, terms, advice, fibo_names):
        """แสดงผลการวิเคราะห์เหรียญ"""
        try:
            btc_trend = btc_analysis.get('primary', {}).get('trend', 'NEUTRAL')
            btc_signal = btc_analysis.get('primary', {}).get('signal', 'CONSOLIDATION')
            
            signal = coin_data['signal']
            signal_text = terms[signal]
            signal_color = "green" if "BREAKOUT" in signal else "red" if "BREAKDOWN" in signal else "yellow"
            score_10 = coin_data.get('score_10', 0)
            
            console.print(f"\n[blue]===== การวิเคราะห์ {symbol} =====")
            console.print(f"[{signal_color}]สัญญาณปัจจุบัน: {signal_text} (คะแนน: {score_10:.1f}/10 | {coin_data['momentum_score']:.2f})[/{signal_color}]")
            
            btc_corr = coin_data.get('btc_correlation', 0)
            btc_aligned = coin_data.get('btc_aligned', False)
            corr_color = "green" if btc_aligned else "red"
            btc_corr_text = f"สหสัมพันธ์กับ BTC: [{corr_color}]{btc_corr:.2f}[/{corr_color}] | สอดคล้องกับแนวโน้ม BTC: [{'green' if btc_aligned else 'red'}]{'ใช่' if btc_aligned else 'ไม่'}[/]"
            
            console.print(f"[white]{btc_corr_text}")
            
            price = coin_data['price']
            price_change_1d = coin_data['extra']['price_change_1d']
            price_change_3d = coin_data['extra']['price_change_3d']
            
            console.print(f"[white]ราคา: {price:.6f} | เปลี่ยน 24h: [{'green' if price_change_1d > 0 else 'red'}]{price_change_1d:+.2f}%[/] | เปลี่ยน 3 วัน: [{'green' if price_change_3d > 0 else 'red'}]{price_change_3d:+.2f}%[/]")
            
            higher_tf_trend = coin_data.get('higher_tf_trend', 'NEUTRAL')
            higher_tf_score = coin_data.get('higher_tf_score', 0)
            trend_color = "green" if higher_tf_trend == 'UPTREND' else "red" if higher_tf_trend == 'DOWNTREND' else "yellow"
            
            console.print(f"[white]แนวโน้ม 4H: [{trend_color}]{higher_tf_trend}[/{trend_color}] | คะแนน 4H: {higher_tf_score:+.1f}")
            
            rsi = coin_data['extra']['rsi']
            macd = coin_data['extra']['macd']
            macd_hist = coin_data['extra']['macd_hist']
            volume_ratio = coin_data['extra']['volume_ratio']
            
            console.print(f"[white]RSI: [{'red' if rsi > 70 else 'green' if rsi < 30 else 'white'}]{rsi:.1f}[/] | MACD: [{'green' if macd > 0 else 'red'}]{macd:.6f}[/] | MACD Histogram: [{'green' if macd_hist > 0 else 'red'}]{macd_hist:.6f}[/] | ปริมาณ: [{'green' if volume_ratio > 1.5 else 'white'}]{volume_ratio:.1f}x[/]")
            
            # แสดงข้อมูล Fibonacci
            self._display_fibonacci_levels(coin_data, console, fibo_names, price)
            
            # แสดงข้อมูลแนวรับแนวต้าน
            self._display_support_resistance(coin_data, console, fibo_names)
            
            # แสดงรูปแบบกราฟที่พบ
            if coin_data['pattern']:
                console.print("[white]รูปแบบที่พบ:")
                for pattern in coin_data['pattern']:
                    if "(4H)" in pattern: 
                        console.print(f"[yellow]- {pattern}[/yellow]")
                    else:
                        color = "green" if any(bullish in pattern.lower() for bullish in [
                            'ทะลุแนวต้าน', 'สามเหลี่ยมฐานยก', 'ลิ่มเอียงลง', 'ธงกระทิง', 
                            'หัวและไหล่กลับหัว', 'ฐานคู่', 'ค้อน', 'แท่งเขียวกลืนแท่งแดง', 'ตัดขึ้น'
                        ]) else "red"
                        console.print(f"[{color}]- {pattern}[/{color}]")
            
            # แสดงสัญญาณพิเศษ
            extra = coin_data['extra']
            if extra['squeeze_fire']: 
                console.print("[magenta]🔥 Volatility Squeeze - โอกาสเกิดการเคลื่อนไหวรุนแรง[/magenta]")
            if extra['trend_reversal']: 
                console.print("[yellow]⚠️ สัญญาณกลับตัวของแนวโน้ม - อาจเกิดการเปลี่ยนทิศทาง[/yellow]")
            
            # แสดงคำแนะนำและระดับการเทรด
            console.print(f"\n[white]คำแนะนำ: [{signal_color}]{advice[signal]}[/{signal_color}]")
            
            entry_price = coin_data.get('entry', price)
            stop_loss = coin_data.get('stop_loss')
            take_profit = coin_data.get('take_profit')
            
            if "BREAKOUT" in signal or "BREAKDOWN" in signal:
                console.print(f"[white]การจัดการความเสี่ยง:")
                console.print(f"- จุดเข้า: {entry_price:.6f} {'(รอ Retest แนวต้านเดิม)' if 'BREAKOUT' in signal else '(รอ Retest แนวรับเดิม)' if 'BREAKDOWN' in signal else ''}")
                
                if stop_loss: 
                    sl_level = ""
                    if coin_data.get('fibo_support_level') and 'BREAKOUT' in signal and abs(stop_loss - coin_data.get('fibo_support', 0)) < 0.0001:
                        sl_level = f" ({fibo_names.get(coin_data['fibo_support_level'], str(coin_data['fibo_support_level']))})"
                    if coin_data.get('fibo_resistance_level') and 'BREAKDOWN' in signal and abs(stop_loss - coin_data.get('fibo_resistance', 0)) < 0.0001:
                        sl_level = f" ({fibo_names.get(coin_data['fibo_resistance_level'], str(coin_data['fibo_resistance_level']))})"
                    console.print(f"- จุดตัดขาดทุน: {stop_loss:.6f}{sl_level}")
                
                if take_profit: 
                    tp_level = ""
                    fibo_levels = coin_data.get('fibo_levels', {})
                    
                    if 'BREAKOUT' in signal and fibo_levels and 'extension' in fibo_levels:
                        for level, price_val in [(float(k), float(v)) for k, v in fibo_levels['extension'].items() if float(k) > 1]:
                            if abs(take_profit - price_val) < 0.0001:
                                tp_level = f" ({fibo_names.get(level, str(level))})"
                                break
                    
                    if 'BREAKDOWN' in signal and fibo_levels and 'extension' in fibo_levels:
                        for level, price_val in [(float(k), float(v)) for k, v in fibo_levels['extension'].items() if float(k) > 1]:
                            if abs(take_profit - price_val) < 0.0001:
                                tp_level = f" ({fibo_names.get(level, str(level))})"
                                break
                    
                    console.print(f"- เป้าหมาย: {take_profit:.6f}{tp_level}")
                
                if stop_loss and take_profit:
                    risk = abs(entry_price - stop_loss)
                    reward = abs(take_profit - entry_price)
                    rr_ratio = reward / risk if risk > 0 else 0
                    console.print(f"- Risk:Reward Ratio: {rr_ratio:.2f}:1")
            
            if btc_aligned and abs(btc_corr) > 0.7:
                console.print(f"[green]👍 สัญญาณสอดคล้องกับแนวโน้มของ Bitcoin - เพิ่มความมั่นใจในการเทรด[/green]")
            elif not btc_aligned and abs(btc_corr) > 0.7:
                console.print(f"[red]⚠️ สัญญาณขัดแย้งกับแนวโน้มของ Bitcoin - ควรระมัดระวังในการเทรด[/red]")
            
            console.print(f"[blue]=====================================[/blue]\n")
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ {symbol}: {str(e)}")
            console.print(f"[red]เกิดข้อผิดพลาดในการแสดงการวิเคราะห์: {str(e)}[/red]")
    
    def _display_fibonacci_levels(self, coin_data, console, fibo_names, price):
        """แสดงระดับ Fibonacci Retracement และ Extension"""
        try:
            fibo_levels = coin_data.get('fibo_levels', {})
            
            console.print("\n[white]ระดับ Fibonacci:")
            fibo_direction = fibo_levels.get('direction', 'ไม่พบข้อมูล')
            console.print(f"[white]ทิศทาง Fibonacci: [{'green' if fibo_direction == 'up' else 'red' if fibo_direction == 'down' else 'yellow'}]{fibo_direction}[/]")
            
            if fibo_direction == 'up':
                swing_high = fibo_levels.get('swing_high')
                swing_low = fibo_levels.get('swing_low')
                if swing_high and swing_low:
                    console.print(f"[white]จุดสูงสุด: {swing_high:.6f} | จุดต่ำสุด: {swing_low:.6f}")
                
                if 'retracement' in fibo_levels and isinstance(fibo_levels['retracement'], dict):
                    console.print("[white]ระดับ Retracement (แนวรับ):")
                    try:
                        levels = fibo_levels['retracement']
                        
                        # แปลง string keys เป็น float
                        if isinstance(levels, dict):
                            sorted_levels = sorted([(float(k), float(v)) for k, v in levels.items()], key=lambda x: x[0])
                            
                            for level, price_at_level in sorted_levels:
                                level_name = fibo_names.get(level, f"{level*100}%")
                                distance = ((price - price_at_level) / price) * 100
                                
                                if price_at_level < price:
                                    console.print(f"  {level_name}: {price_at_level:.6f} ([green]รองรับ[/green], ห่าง {abs(distance):.1f}%)")
                                else:
                                    console.print(f"  {level_name}: {price_at_level:.6f} ([red]ต้านทาน[/red], ห่าง {abs(distance):.1f}%)")
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงระดับ Retracement: {str(e)}")
                
                if 'extension' in fibo_levels and isinstance(fibo_levels['extension'], dict):
                    console.print("[white]ระดับ Extension (เป้าหมาย):")
                    try:
                        levels = fibo_levels['extension']
                        
                        # แปลง string keys เป็น float
                        if isinstance(levels, dict):
                            sorted_levels = sorted([(float(k), float(v)) for k, v in levels.items() if float(k) > 1], key=lambda x: x[0])
                            
                            for level, price_at_level in sorted_levels:
                                level_name = fibo_names.get(level, f"{level*100}%")
                                distance = ((price_at_level - price) / price) * 100
                                console.print(f"  {level_name}: {price_at_level:.6f} (เป้าหมาย, ห่าง {distance:.1f}%)")
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงระดับ Extension: {str(e)}")
            
            elif fibo_direction == 'down':
                swing_high = fibo_levels.get('swing_high')
                swing_low = fibo_levels.get('swing_low')
                if swing_high and swing_low:
                    console.print(f"[white]จุดสูงสุด: {swing_high:.6f} | จุดต่ำสุด: {swing_low:.6f}")
                
                if 'retracement' in fibo_levels and isinstance(fibo_levels['retracement'], dict):
                    console.print("[white]ระดับ Retracement (แนวต้าน):")
                    try:
                        levels = fibo_levels['retracement']
                        
                        # แปลง string keys เป็น float
                        if isinstance(levels, dict):
                            sorted_levels = sorted([(float(k), float(v)) for k, v in levels.items()], key=lambda x: x[0])
                            
                            for level, price_at_level in sorted_levels:
                                level_name = fibo_names.get(level, f"{level*100}%")
                                distance = ((price_at_level - price) / price) * 100
                                
                                if price_at_level > price:
                                    console.print(f"  {level_name}: {price_at_level:.6f} ([red]ต้านทาน[/red], ห่าง {abs(distance):.1f}%)")
                                else:
                                    console.print(f"  {level_name}: {price_at_level:.6f} ([green]รองรับ[/green], ห่าง {abs(distance):.1f}%)")
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงระดับ Retracement: {str(e)}")
                
                if 'extension' in fibo_levels and isinstance(fibo_levels['extension'], dict):
                    console.print("[white]ระดับ Extension (เป้าหมาย):")
                    try:
                        levels = fibo_levels['extension']
                        
                        # แปลง string keys เป็น float
                        if isinstance(levels, dict):
                            sorted_levels = sorted([(float(k), float(v)) for k, v in levels.items() if float(k) > 1], key=lambda x: x[0])
                            
                            for level, price_at_level in sorted_levels:
                                level_name = fibo_names.get(level, f"{level*100}%")
                                distance = ((price - price_at_level) / price) * 100
                                console.print(f"  {level_name}: {price_at_level:.6f} (เป้าหมาย, ห่าง {abs(distance):.1f}%)")
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงระดับ Extension: {str(e)}")
                        
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงระดับ Fibonacci: {str(e)}")
    
    def _display_support_resistance(self, coin_data, console, fibo_names):
        """แสดงระดับแนวรับแนวต้าน"""
        try:
            nearest_resistance = coin_data['extra']['nearest_resistance']
            nearest_support = coin_data['extra']['nearest_support']
            distance_to_resistance = coin_data['extra']['distance_to_resistance']
            distance_to_support = coin_data['extra']['distance_to_support']
            higher_tf_resistance = coin_data['extra']['higher_tf_resistance']
            higher_tf_support = coin_data['extra']['higher_tf_support']
            fibo_support = coin_data.get('fibo_support')
            fibo_resistance = coin_data.get('fibo_resistance')
            fibo_support_level = coin_data.get('fibo_support_level')
            fibo_resistance_level = coin_data.get('fibo_resistance_level')
            
            console.print("\n[white]ระดับแนวรับแนวต้าน:")
            
            if nearest_resistance: 
                console.print(f"[white]แนวต้านถัดไป (1H): {nearest_resistance:.6f} (ห่าง {distance_to_resistance:.1f}%)")
            if nearest_support: 
                console.print(f"[white]แนวรับถัดไป (1H): {nearest_support:.6f} (ห่าง {distance_to_support:.1f}%)")
            if higher_tf_resistance: 
                console.print(f"[white]แนวต้านถัดไป (4H): {higher_tf_resistance:.6f}")
            if higher_tf_support: 
                console.print(f"[white]แนวรับถัดไป (4H): {higher_tf_support:.6f}")
            
            if fibo_resistance and (nearest_resistance is None or abs(fibo_resistance - nearest_resistance) > 0.0001):
                console.print(f"[white]แนวต้าน Fibonacci: {fibo_resistance:.6f} ({fibo_names.get(fibo_resistance_level, str(fibo_resistance_level))})")
            if fibo_support and (nearest_support is None or abs(fibo_support - nearest_support) > 0.0001):
                console.print(f"[white]แนวรับ Fibonacci: {fibo_support:.6f} ({fibo_names.get(fibo_support_level, str(fibo_support_level))})")
                
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงแนวรับแนวต้าน: {str(e)}")
    
    def display_btc_analysis(self, btc_analysis, console, terms, advice, fibo_names):
        """แสดงผลการวิเคราะห์ Bitcoin"""
        try:
            tf_1h = btc_analysis.get('1h', {})
            tf_4h = btc_analysis.get('4h', {})
            tf_1d = btc_analysis.get('1d', {})
            primary = btc_analysis.get('primary', {})
            
            console.print(f"\n[blue]===== การวิเคราะห์ Bitcoin (BTCUSDT) =====")
            price = tf_1h.get('price', 0)
            console.print(f"[white]ราคาปัจจุบัน: ${price:,.2f}")
            
            primary_trend = primary.get('trend', 'NEUTRAL')
            primary_signal = primary.get('signal', 'CONSOLIDATION')
            primary_score = primary.get('momentum_score', 0)
            primary_score_10 = primary.get('score_10', 0)
            
            trend_color = "green" if primary_trend == 'UPTREND' else "red" if primary_trend == 'DOWNTREND' else "yellow"
            signal_color = "green" if "BREAKOUT" in primary_signal else "red" if "BREAKDOWN" in primary_signal else "yellow"
            signal_text = terms.get(primary_signal, 'กำลังสะสม')
            
            console.print(f"[{trend_color}]แนวโน้มหลัก: {primary_trend}[/{trend_color}] | [{signal_color}]สัญญาณ: {signal_text}[/{signal_color}] | คะแนนรวม: {primary_score_10:.1f}/10 ({primary_score:.2f})")
            
            console.print("\n[white]รายละเอียดแต่ละกรอบเวลา:")
            
            # 1H Timeframe
            trend_1h = tf_1h.get('trend', 'NEUTRAL')
            score_1h = tf_1h.get('momentum_score', 0)
            score_10_1h = tf_1h.get('score_10', 0)
            signal_1h = tf_1h.get('signal', 'CONSOLIDATION')
            signal_text_1h = terms.get(signal_1h, 'กำลังสะสม')
            
            trend_color_1h = "green" if trend_1h == 'UPTREND' else "red" if trend_1h == 'DOWNTREND' else "yellow"
            signal_color_1h = "green" if "BREAKOUT" in signal_1h else "red" if "BREAKDOWN" in signal_1h else "yellow"
            
            console.print(f"[bold]1H:[/bold] [{trend_color_1h}]{trend_1h}[/{trend_color_1h}] | [{signal_color_1h}]{signal_text_1h}[/{signal_color_1h}] | คะแนน: {score_10_1h:.1f}/10 ({score_1h:.2f})")
            
            extra_1h = tf_1h.get('extra', {})
            rsi_1h = extra_1h.get('rsi', 0)
            macd_1h = extra_1h.get('macd', 0)
            volume_ratio_1h = extra_1h.get('volume_ratio', 0)
            change_1d_1h = extra_1h.get('change_1d', 0)
            
            console.print(f"  RSI: [{'red' if rsi_1h > 70 else 'green' if rsi_1h < 30 else 'white'}]{rsi_1h:.1f}[/] | MACD: [{'green' if macd_1h > 0 else 'red'}]{macd_1h:.6f}[/] | ปริมาณ: [{'green' if volume_ratio_1h > 1.5 else 'white'}]{volume_ratio_1h:.1f}x[/] | เปลี่ยน 24h: [{'green' if change_1d_1h > 0 else 'red'}]{change_1d_1h:+.2f}%[/]")
            
            support_1h = extra_1h.get('nearest_support')
            resistance_1h = extra_1h.get('nearest_resistance')
            
            # แสดง Fibonacci 1H
            fibo_levels_1h = tf_1h.get('fibo_levels', {})
            if fibo_levels_1h:
                fibo_direction_1h = fibo_levels_1h.get('direction', 'ไม่พบข้อมูล')
                console.print(f"  Fibonacci Direction: [{'green' if fibo_direction_1h == 'up' else 'red' if fibo_direction_1h == 'down' else 'yellow'}]{fibo_direction_1h}[/]")
                
                if 'retracement' in fibo_levels_1h and isinstance(fibo_levels_1h['retracement'], dict):
                    key_levels = [0.382, 0.5, 0.618, 0.786]
                    for level in key_levels:
                        level_str = str(level)
                        if level_str in fibo_levels_1h['retracement']:
                            level_price = float(fibo_levels_1h['retracement'][level_str])
                            level_name = fibo_names.get(level, f"{level*100}%")
                            
                            if (fibo_direction_1h == 'up' and level_price < price) or (fibo_direction_1h == 'down' and level_price > price):
                                console.print(f"  Fibo Support {level_name}: {level_price:.2f}")
                            else:
                                console.print(f"  Fibo Resistance {level_name}: {level_price:.2f}")
                                
            if support_1h: console.print(f"  แนวรับ: ${support_1h:,.2f}")
            if resistance_1h: console.print(f"  แนวต้าน: ${resistance_1h:,.2f}")
            
            # 4H Timeframe
            trend_4h = tf_4h.get('trend', 'NEUTRAL')
            score_4h = tf_4h.get('momentum_score', 0)
            score_10_4h = tf_4h.get('score_10', 0)
            signal_4h = tf_4h.get('signal', 'CONSOLIDATION')
            signal_text_4h = terms.get(signal_4h, 'กำลังสะสม')
            
            trend_color_4h = "green" if trend_4h == 'UPTREND' else "red" if trend_4h == 'DOWNTREND' else "yellow"
            signal_color_4h = "green" if "BREAKOUT" in signal_4h else "red" if "BREAKDOWN" in signal_4h else "yellow"
            
            console.print(f"\n[bold]4H:[/bold] [{trend_color_4h}]{trend_4h}[/{trend_color_4h}] | [{signal_color_4h}]{signal_text_4h}[/{signal_color_4h}] | คะแนน: {score_10_4h:.1f}/10 ({score_4h:.2f})")
            
            extra_4h = tf_4h.get('extra', {})
            rsi_4h = extra_4h.get('rsi', 0)
            macd_4h = extra_4h.get('macd', 0)
            
            console.print(f"  RSI: [{'red' if rsi_4h > 70 else 'green' if rsi_4h < 30 else 'white'}]{rsi_4h:.1f}[/] | MACD: [{'green' if macd_4h > 0 else 'red'}]{macd_4h:.6f}[/]")
            
            support_4h = extra_4h.get('nearest_support')
            resistance_4h = extra_4h.get('nearest_resistance')
            
            # แสดง Fibonacci 4H
            fibo_levels_4h = tf_4h.get('fibo_levels', {})
            if fibo_levels_4h:
                fibo_direction_4h = fibo_levels_4h.get('direction', 'ไม่พบข้อมูล')
                console.print(f"  Fibonacci Direction: [{'green' if fibo_direction_4h == 'up' else 'red' if fibo_direction_4h == 'down' else 'yellow'}]{fibo_direction_4h}[/]")
                
                if 'retracement' in fibo_levels_4h and isinstance(fibo_levels_4h['retracement'], dict):
                    key_levels = [0.382, 0.5, 0.618, 0.786]
                    for level in key_levels:
                        level_str = str(level)
                        if level_str in fibo_levels_4h['retracement']:
                            level_price = float(fibo_levels_4h['retracement'][level_str])
                            level_name = fibo_names.get(level, f"{level*100}%")
                            
                            if (fibo_direction_4h == 'up' and level_price < price) or (fibo_direction_4h == 'down' and level_price > price):
                                console.print(f"  Fibo Support {level_name}: {level_price:.2f}")
                            else:
                                console.print(f"  Fibo Resistance {level_name}: {level_price:.2f}")
                                
            if support_4h: console.print(f"  แนวรับ: ${support_4h:,.2f}")
            if resistance_4h: console.print(f"  แนวต้าน: ${resistance_4h:,.2f}")
            
            # 1D Timeframe
            trend_1d = tf_1d.get('trend', 'NEUTRAL')
            score_1d = tf_1d.get('momentum_score', 0)
            score_10_1d = tf_1d.get('score_10', 0)
            signal_1d = tf_1d.get('signal', 'CONSOLIDATION')
            signal_text_1d = terms.get(signal_1d, 'กำลังสะสม')
            
            trend_color_1d = "green" if trend_1d == 'UPTREND' else "red" if trend_1d == 'DOWNTREND' else "yellow"
            signal_color_1d = "green" if "BREAKOUT" in signal_1d else "red" if "BREAKDOWN" in signal_1d else "yellow"
            
            console.print(f"\n[bold]1D:[/bold] [{trend_color_1d}]{trend_1d}[/{trend_color_1d}] | [{signal_color_1d}]{signal_text_1d}[/{signal_color_1d}] | คะแนน: {score_10_1d:.1f}/10 ({score_1d:.2f})")
            
            extra_1d = tf_1d.get('extra', {})
            rsi_1d = extra_1d.get('rsi', 0)
            macd_1d = extra_1d.get('macd', 0)
            
            console.print(f"  RSI: [{'red' if rsi_1d > 70 else 'green' if rsi_1d < 30 else 'white'}]{rsi_1d:.1f}[/] | MACD: [{'green' if macd_1d > 0 else 'red'}]{macd_1d:.6f}[/]")
            
            support_1d = extra_1d.get('nearest_support')
            resistance_1d = extra_1d.get('nearest_resistance')
            
            # แสดง Fibonacci 1D
            fibo_levels_1d = tf_1d.get('fibo_levels', {})
            if fibo_levels_1d:
                fibo_direction_1d = fibo_levels_1d.get('direction', 'ไม่พบข้อมูล')
                console.print(f"  Fibonacci Direction: [{'green' if fibo_direction_1d == 'up' else 'red' if fibo_direction_1d == 'down' else 'yellow'}]{fibo_direction_1d}[/]")
                
                if 'retracement' in fibo_levels_1d and isinstance(fibo_levels_1d['retracement'], dict):
                    key_levels = [0.382, 0.5, 0.618, 0.786]
                    for level in key_levels:
                        level_str = str(level)
                        if level_str in fibo_levels_1d['retracement']:
                            level_price = float(fibo_levels_1d['retracement'][level_str])
                            level_name = fibo_names.get(level, f"{level*100}%")
                            
                            if (fibo_direction_1d == 'up' and level_price < price) or (fibo_direction_1d == 'down' and level_price > price):
                                console.print(f"  Fibo Support {level_name}: {level_price:.2f}")
                            else:
                                console.print(f"  Fibo Resistance {level_name}: {level_price:.2f}")
                                
            if support_1d: console.print(f"  แนวรับ: ${support_1d:,.2f}")
            if resistance_1d: console.print(f"  แนวต้าน: ${resistance_1d:,.2f}")
            
            # แสดงรูปแบบกราฟที่พบ
            patterns_1h = tf_1h.get('patterns', [])
            patterns_4h = tf_4h.get('patterns', [])
            patterns_1d = tf_1d.get('patterns', [])
            
            if patterns_1h or patterns_4h or patterns_1d:
                console.print("\n[white]รูปแบบกราฟที่พบ:")
                
                if patterns_1h:
                    console.print("[bold]1H:[/bold]")
                    for pattern in patterns_1h:
                        color = "green" if any(bullish in pattern.lower() for bullish in [
                            'ทะลุแนวต้าน', 'สามเหลี่ยมฐานยก', 'ลิ่มเอียงลง', 'ธงกระทิง', 
                            'หัวและไหล่กลับหัว', 'ฐานคู่', 'ค้อน', 'แท่งเขียวกลืนแท่งแดง', 'ตัดขึ้น'
                        ]) else "red"
                        console.print(f"  [{color}]- {pattern}[/{color}]")
                
                if patterns_4h:
                    console.print("[bold]4H:[/bold]")
                    for pattern in patterns_4h:
                        color = "green" if any(bullish in pattern.lower() for bullish in [
                            'ทะลุแนวต้าน', 'สามเหลี่ยมฐานยก', 'ลิ่มเอียงลง', 'ธงกระทิง', 
                            'หัวและไหล่กลับหัว', 'ฐานคู่', 'ค้อน', 'แท่งเขียวกลืนแท่งแดง', 'ตัดขึ้น'
                        ]) else "red"
                        console.print(f"  [{color}]- {pattern}[/{color}]")
                
                if patterns_1d:
                    console.print("[bold]1D:[/bold]")
                    for pattern in patterns_1d:
                        color = "green" if any(bullish in pattern.lower() for bullish in [
                            'ทะลุแนวต้าน', 'สามเหลี่ยมฐานยก', 'ลิ่มเอียงลง', 'ธงกระทิง', 
                            'หัวและไหล่กลับหัว', 'ฐานคู่', 'ค้อน', 'แท่งเขียวกลืนแท่งแดง', 'ตัดขึ้น'
                        ]) else "red"
                        console.print(f"  [{color}]- {pattern}[/{color}]")
            
            console.print("\n[white]คำแนะนำสำหรับตลาด:")
            
            if primary_trend == 'UPTREND':
                console.print("[green]👍 ตลาดอยู่ในแนวโน้มขาขึ้น - เน้นการหาจังหวะเข้า Long และหลีกเลี่ยงการ Short[/green]")
            elif primary_trend == 'DOWNTREND':
                console.print("[red]👎 ตลาดอยู่ในแนวโน้มขาลง - เน้นการหาจังหวะเข้า Short และระมัดระวังการ Long[/red]")
            else:
                console.print("[yellow]⚠️ ตลาดอยู่ในแนวโน้ม Neutral - ควรรอสัญญาณที่ชัดเจนก่อนเข้าเทรด[/yellow]")
            
            console.print("\n[white]สรุปการเทรดตามกรอบเวลา:")
            
            if signal_1h in ['STRONG_BREAKOUT', 'BREAKOUT']:
                console.print("[green]1H: เหมาะสำหรับการเข้า Long ระยะสั้น (1-2 วัน)[/green]")
            elif signal_1h in ['STRONG_BREAKDOWN', 'BREAKDOWN']:
                console.print("[red]1H: เหมาะสำหรับการเข้า Short ระยะสั้น (1-2 วัน)[/red]")
            else:
                console.print("[yellow]1H: ยังไม่มีสัญญาณชัดเจนสำหรับการเทรดระยะสั้น[/yellow]")
            
            if signal_4h in ['STRONG_BREAKOUT', 'BREAKOUT']:
                console.print("[green]4H: เหมาะสำหรับการเข้า Long ระยะกลาง (3-7 วัน)[/green]")
            elif signal_4h in ['STRONG_BREAKDOWN', 'BREAKDOWN']:
                console.print("[red]4H: เหมาะสำหรับการเข้า Short ระยะกลาง (3-7 วัน)[/red]")
            else:
                console.print("[yellow]4H: ยังไม่มีสัญญาณชัดเจนสำหรับการเทรดระยะกลาง[/yellow]")
            
            if signal_1d in ['STRONG_BREAKOUT', 'BREAKOUT']:
                console.print("[green]1D: เหมาะสำหรับการเข้า Long ระยะยาว (1-4 สัปดาห์)[/green]")
            elif signal_1d in ['STRONG_BREAKDOWN', 'BREAKDOWN']:
                console.print("[red]1D: เหมาะสำหรับการเข้า Short ระยะยาว (1-4 สัปดาห์)[/red]")
            else:
                console.print("[yellow]1D: ยังไม่มีสัญญาณชัดเจนสำหรับการเทรดระยะยาว[/yellow]")
            
            # แสดงกลยุทธ์ Fibonacci
            self._display_fibonacci_strategy(tf_1h, tf_4h, tf_1d, primary_trend, console, fibo_names, price)
            
            console.print(f"[blue]=====================================[/blue]\n")
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ Bitcoin: {str(e)}")
            console.print(f"[red]เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ Bitcoin: {str(e)}[/red]")
    
    def _display_fibonacci_strategy(self, tf_1h, tf_4h, tf_1d, primary_trend, console, fibo_names, price):
        """แสดงกลยุทธ์การเทรดตามระดับ Fibonacci"""
        try:
            console.print("\n[white]กลยุทธ์เทรดตามระดับ Fibonacci:")
            
            # แสดงกลยุทธ์สำหรับแนวโน้มขาขึ้น
            if primary_trend == 'UPTREND':
                key_buy_levels = [0.5, 0.618, 0.786]
                key_tp_levels = [1.0, 1.618, 2.618]
                
                console.print("[green]กลยุทธ์สำหรับแนวโน้มขาขึ้น:[/green]")
                
                # ดึงระดับ Fibonacci จาก timeframe ที่เหมาะสมที่สุด
                fibo_data = None
                if 'fibo_levels' in tf_1d and tf_1d['fibo_levels'] and tf_1d['fibo_levels'].get('direction') == 'up':
                    fibo_data = tf_1d['fibo_levels']
                    tf_text = "1D"
                elif 'fibo_levels' in tf_4h and tf_4h['fibo_levels'] and tf_4h['fibo_levels'].get('direction') == 'up':
                    fibo_data = tf_4h['fibo_levels']
                    tf_text = "4H"
                elif 'fibo_levels' in tf_1h and tf_1h['fibo_levels'] and tf_1h['fibo_levels'].get('direction') == 'up':
                    fibo_data = tf_1h['fibo_levels']
                    tf_text = "1H"
                
                if fibo_data and 'retracement' in fibo_data and 'extension' in fibo_data:
                    try:
                        retracement = fibo_data['retracement']
                        extension = fibo_data['extension']
                        
                        # แปลง string keys เป็น float หากจำเป็น
                        if isinstance(retracement, dict) and isinstance(extension, dict):
                            retracement = {float(k): float(v) for k, v in retracement.items()}
                            extension = {float(k): float(v) for k, v in extension.items()}
                            
                            console.print(f"[white]จุดซื้อที่แนะนำ ({tf_text}):")
                            for level in key_buy_levels:
                                if level in retracement:
                                    level_price = retracement[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- ซื้อที่ระดับ {level_name}: ${level_price:,.2f}")
                            
                            console.print(f"[white]เป้าหมายกำไร ({tf_text}):")
                            tp_count = 1
                            for level in key_tp_levels:
                                if level <= 1.0 and level in retracement:
                                    level_price = retracement[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- TP{tp_count}: {level_name}: ${level_price:,.2f}")
                                    tp_count += 1
                                elif level > 1.0 and level in extension:
                                    level_price = extension[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- TP{tp_count}: {level_name}: ${level_price:,.2f}")
                                    tp_count += 1
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงกลยุทธ์ Fibonacci ขาขึ้น: {str(e)}")
            
            # แสดงกลยุทธ์สำหรับแนวโน้มขาลง
            elif primary_trend == 'DOWNTREND':
                key_sell_levels = [0.5, 0.618, 0.786]
                key_tp_levels = [1.0, 1.618, 2.618]
                
                console.print("[red]กลยุทธ์สำหรับแนวโน้มขาลง:[/red]")
                
                # ดึงระดับ Fibonacci จาก timeframe ที่เหมาะสมที่สุด
                fibo_data = None
                if 'fibo_levels' in tf_1d and tf_1d['fibo_levels'] and tf_1d['fibo_levels'].get('direction') == 'down':
                    fibo_data = tf_1d['fibo_levels']
                    tf_text = "1D"
                elif 'fibo_levels' in tf_4h and tf_4h['fibo_levels'] and tf_4h['fibo_levels'].get('direction') == 'down':
                    fibo_data = tf_4h['fibo_levels']
                    tf_text = "4H"
                elif 'fibo_levels' in tf_1h and tf_1h['fibo_levels'] and tf_1h['fibo_levels'].get('direction') == 'down':
                    fibo_data = tf_1h['fibo_levels']
                    tf_text = "1H"
                
                if fibo_data and 'retracement' in fibo_data and 'extension' in fibo_data:
                    try:
                        retracement = fibo_data['retracement']
                        extension = fibo_data['extension']
                        
                        # แปลง string keys เป็น float หากจำเป็น
                        if isinstance(retracement, dict) and isinstance(extension, dict):
                            retracement = {float(k): float(v) for k, v in retracement.items()}
                            extension = {float(k): float(v) for k, v in extension.items()}
                            
                            console.print(f"[white]จุดขายที่แนะนำ ({tf_text}):")
                            for level in key_sell_levels:
                                if level in retracement:
                                    level_price = retracement[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- ขายที่ระดับ {level_name}: ${level_price:,.2f}")
                            
                            console.print(f"[white]เป้าหมายกำไร ({tf_text}):")
                            tp_count = 1
                            for level in key_tp_levels:
                                if level <= 1.0 and level in retracement:
                                    level_price = retracement[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- TP{tp_count}: {level_name}: ${level_price:,.2f}")
                                    tp_count += 1
                                elif level > 1.0 and level in extension:
                                    level_price = extension[level]
                                    level_name = fibo_names.get(level, f"{level*100}%")
                                    console.print(f"- TP{tp_count}: {level_name}: ${level_price:,.2f}")
                                    tp_count += 1
                    except Exception as e:
                        self.logger.error(f"เกิดข้อผิดพลาดในการแสดงกลยุทธ์ Fibonacci ขาลง: {str(e)}")
                    
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการแสดงกลยุทธ์ Fibonacci: {str(e)}")