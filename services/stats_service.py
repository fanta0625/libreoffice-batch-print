# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from models.file_model import FileItem,DuplexMode

class StatsService:

    @staticmethod
    def parse_page_ranges(range_str: str, max_pages: int) -> int:
        """
        解析页码范围字符串，返回实际包含的页数总数。
        支持格式: "1-5", "1,3,5", "1-3,5,7-9"
        
        :param range_str: 用户输入的字符串，如 "1-3,4"
        :param max_pages: 文档总页数，用于校验和限制范围
        :return: 实际选中的页数总和
        """
        if not range_str or range_str == "1-?":
            return 0
            
        total_count = 0
        parts = range_str.split(",")
        
        try:
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if "-" in part:
                    # 处理范围 "1-3"
                    sub_parts = part.split("-")
                    if len(sub_parts) != 2:
                        continue # 跳过非法格式
                    
                    start_p = int(sub_parts[0])
                    end_p = int(sub_parts[1])
                    
                    # 确保不超过文档最大页数，且不小于1
                    start_p = max(1, start_p)
                    end_p = min(max_pages, end_p)
                    
                    if start_p <= end_p:
                        total_count += (end_p - start_p + 1)
                else:
                    # 处理单页 "4"
                    p = int(part)
                    if 1 <= p <= max_pages:
                        total_count += 1
        except ValueError:
            # 如果包含非数字字符，返回 0 或当前已计算的部分
            return 0
            
        return total_count

    @staticmethod
    def calculate_for_selection(selected_items: list) -> dict:
        """
        计算选中项的总页数和总用纸量
        """
        total_pages = 0
        total_sheets = 0

        for item in selected_items:
            # 获取用户设定的页码范围字符串
            range_str = getattr(item, 'page_range', None)
            if not range_str and hasattr(item, 'params'):
                range_str = getattr(item.params, 'page_range', None)
            
            # 如果没有设置范围，或者范围无效，默认打印全部
            if not range_str or range_str == "1-?":
                effective_pages = item.total_pages
            else:
                # 解析复杂范围 (如 "1-3,4")
                effective_pages = StatsService.parse_page_ranges(range_str, item.total_pages)
            
            # 如果解析结果为0（例如输入错误），可以选择跳过或按0计算
            if effective_pages <= 0:
                continue

            copies = item.params.copies if hasattr(item, 'params') and hasattr(item.params, 'copies') else 1
            
            # 计算总页数
            pages_with_copies = effective_pages * copies
            
            # 计算用纸量 (考虑双面打印)
            sheets_for_item = pages_with_copies
            
            duplex_mode = None
            if hasattr(item, 'params') and hasattr(item.params, 'duplex_mode'):
                duplex_mode = item.params.duplex_mode
            
            if duplex_mode is not None and duplex_mode != DuplexMode.NONE:
                # 双面打印：向上取整 (pages + 1) // 2
                sheets_for_item = (pages_with_copies + 1) // 2
            
            # 累加
            total_pages += pages_with_copies
            total_sheets += sheets_for_item
        return {
            "count": len(selected_items),
            "pages": total_pages,      
            "sheets": total_sheets   
        }

    # 在 stats_service.py 的 StatsService 类中添加以下方法

    @staticmethod
    def get_page_indices(range_str: str, max_pages: int) -> list[int]:
        """
        解析页码范围字符串，返回一个包含所有选中页码的列表（从0开始索引）。
        支持格式: "1-5", "1,3,5", "1-3,5,7-9"
        
        :param range_str: 用户输入的字符串，如 "1-3,4"
        :param max_pages: 文档总页数，用于校验和限制范围
        :return: 包含所有选中页码的列表，页码从0开始。例如 [0, 1, 2, 4]
        """
        if not range_str or range_str == "1-?":
            return list(range(max_pages)) # 如果没有指定范围，默认返回所有页

        page_indices = []
        parts = range_str.split(",")
        
        try:
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if "-" in part:
                    # 处理范围 "1-3"
                    sub_parts = part.split("-")
                    if len(sub_parts) != 2:
                        continue # 跳过非法格式
                    
                    start_p = int(sub_parts[0])
                    end_p = int(sub_parts[1])
                    
                    # 确保范围有效且在文档页数内
                    start_p = max(1, start_p)
                    end_p = min(max_pages, end_p)
                    
                    if start_p <= end_p:
                        # 将1-based页码转换为0-based索引并添加到列表
                        page_indices.extend(range(start_p - 1, end_p))
                else:
                    # 处理单页 "4"
                    p = int(part)
                    if 1 <= p <= max_pages:
                        page_indices.append(p - 1) 
                        
        except ValueError:
            # 如果包含非数字字符，返回空列表
            return []
        
        # 去重并排序，以防用户输入如 "1,3,1"
        return sorted(list(set(page_indices)))
